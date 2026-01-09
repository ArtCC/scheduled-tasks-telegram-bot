"""SQLite-based persistent storage for scheduled tasks.

This module provides the TaskStorage class that handles all database operations
including CRUD operations for tasks and automatic schema migrations.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .models import Task


class TaskStorage:
    """SQLite storage backend for tasks.

    Handles database initialization, schema migrations, and all CRUD operations
    for Task objects. The database is created automatically if it doesn't exist.

    Attributes:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        """Initialize the storage with a database path.

        Args:
            db_path: Path to the SQLite database file. Parent directories
                     will be created if they don't exist.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Create a new database connection.

        Returns:
            SQLite connection with Row factory enabled.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database schema and run migrations.

        Creates the tasks table if it doesn't exist and adds any missing
        columns for backwards compatibility with older database versions.
        """
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    prompt TEXT NOT NULL,
                    hour INTEGER NOT NULL,
                    minute INTEGER NOT NULL,
                    timezone TEXT NOT NULL,
                    run_at TEXT,
                    paused INTEGER NOT NULL DEFAULT 0,
                    interval_minutes INTEGER,
                    name TEXT,
                    days_of_week TEXT,
                    is_reminder INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # Migration: add columns if they don't exist
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]
            if "paused" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN paused INTEGER NOT NULL DEFAULT 0")
            if "interval_minutes" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN interval_minutes INTEGER")
            if "name" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN name TEXT")
            if "days_of_week" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN days_of_week TEXT")
            if "is_reminder" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN is_reminder INTEGER NOT NULL DEFAULT 0")
            conn.commit()

    def add_task(self, task: Task) -> Task:
        """Add a new task to the database.

        Args:
            task: Task object to persist. The id field will be populated
                  after insertion.

        Returns:
            The same Task object with its id field set.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks
                    (chat_id, prompt, hour, minute, timezone, run_at,
                     paused, interval_minutes, name, days_of_week, is_reminder)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.chat_id,
                    task.prompt,
                    task.hour,
                    task.minute,
                    task.timezone,
                    task.run_at.isoformat() if task.run_at else None,
                    1 if task.paused else 0,
                    task.interval_minutes,
                    task.name,
                    task.days_of_week,
                    1 if task.is_reminder else 0,
                ),
            )
            conn.commit()
            task.id = cursor.lastrowid
            return task

    def set_paused(self, task_id: int, chat_id: int, paused: bool) -> bool:
        """Set the paused state of a task.

        Args:
            task_id: ID of the task to update.
            chat_id: Chat ID that owns the task (for authorization).
            paused: True to pause, False to resume.

        Returns:
            True if the task was found and updated, False otherwise.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET paused = ? WHERE id = ? AND chat_id = ?",
                (1 if paused else 0, task_id, chat_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_task(self, task_id: int, chat_id: int) -> Task | None:
        """Get a single task by ID.

        Args:
            task_id: ID of the task to retrieve.
            chat_id: Chat ID that owns the task (for authorization).

        Returns:
            Task object if found, None otherwise.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND chat_id = ?", (task_id, chat_id)
            ).fetchone()
            return self._row_to_task(row) if row else None

    def update_prompt(self, task_id: int, chat_id: int, new_prompt: str) -> bool:
        """Update the prompt of an existing task.

        Args:
            task_id: ID of the task to update.
            chat_id: Chat ID that owns the task (for authorization).
            new_prompt: New prompt text to set.

        Returns:
            True if the task was found and updated, False otherwise.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET prompt = ? WHERE id = ? AND chat_id = ?",
                (new_prompt, task_id, chat_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_tasks(self, chat_id: int) -> List[Task]:
        """List all tasks for a specific chat.

        Args:
            chat_id: Chat ID to filter tasks by.

        Returns:
            List of Task objects ordered by ID ascending.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE chat_id = ? ORDER BY id ASC", (chat_id,)
            ).fetchall()
            return [self._row_to_task(row) for row in rows]

    def delete_task(self, task_id: int, chat_id: int) -> bool:
        """Delete a task from the database.

        Args:
            task_id: ID of the task to delete.
            chat_id: Chat ID that owns the task (for authorization).

        Returns:
            True if the task was found and deleted, False otherwise.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE id = ? AND chat_id = ?", (task_id, chat_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def load_all(self) -> Iterable[Task]:
        """Load all tasks from the database (all chats).

        Used primarily for restoring scheduled jobs on bot startup.

        Returns:
            Iterable of all Task objects in the database.
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tasks").fetchall()
            return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """Convert a database row to a Task object.

        Args:
            row: SQLite Row object from a query result.

        Returns:
            Task object populated with row data.
        """
        run_at = datetime.fromisoformat(row["run_at"]) if row["run_at"] is not None else None
        # Handle is_reminder column which may not exist in older databases
        is_reminder = bool(row["is_reminder"]) if "is_reminder" in row.keys() else False
        return Task(
            id=row["id"],
            chat_id=row["chat_id"],
            prompt=row["prompt"],
            hour=row["hour"],
            minute=row["minute"],
            timezone=row["timezone"],
            run_at=run_at,
            paused=bool(row["paused"]),
            interval_minutes=row["interval_minutes"],
            name=row["name"],
            days_of_week=row["days_of_week"],
            is_reminder=is_reminder,
        )
