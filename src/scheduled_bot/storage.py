import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .models import Task


class TaskStorage:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
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
                    paused INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # Migration: add paused column if it doesn't exist
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]
            if "paused" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN paused INTEGER NOT NULL DEFAULT 0")
            conn.commit()

    def add_task(self, task: Task) -> Task:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks (chat_id, prompt, hour, minute, timezone, run_at, paused)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.chat_id,
                    task.prompt,
                    task.hour,
                    task.minute,
                    task.timezone,
                    task.run_at.isoformat() if task.run_at else None,
                    1 if task.paused else 0,
                ),
            )
            conn.commit()
            task.id = cursor.lastrowid
            return task

    def set_paused(self, task_id: int, chat_id: int, paused: bool) -> bool:
        """Set the paused state of a task. Returns True if task was found."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET paused = ? WHERE id = ? AND chat_id = ?",
                (1 if paused else 0, task_id, chat_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_task(self, task_id: int, chat_id: int) -> Task | None:
        """Get a single task by ID and chat_id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND chat_id = ?", (task_id, chat_id)
            ).fetchone()
            return self._row_to_task(row) if row else None

    def update_prompt(self, task_id: int, chat_id: int, new_prompt: str) -> bool:
        """Update the prompt of a task. Returns True if task was found."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET prompt = ? WHERE id = ? AND chat_id = ?",
                (new_prompt, task_id, chat_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_tasks(self, chat_id: int) -> List[Task]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE chat_id = ? ORDER BY id ASC", (chat_id,)
            ).fetchall()
            return [self._row_to_task(row) for row in rows]

    def delete_task(self, task_id: int, chat_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE id = ? AND chat_id = ?", (task_id, chat_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def load_all(self) -> Iterable[Task]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tasks").fetchall()
            return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        run_at = datetime.fromisoformat(row["run_at"]) if row["run_at"] is not None else None
        return Task(
            id=row["id"],
            chat_id=row["chat_id"],
            prompt=row["prompt"],
            hour=row["hour"],
            minute=row["minute"],
            timezone=row["timezone"],
            run_at=run_at,
            paused=bool(row["paused"]),
        )
