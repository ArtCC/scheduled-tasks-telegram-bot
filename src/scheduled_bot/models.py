"""Data models for the scheduled tasks bot.

This module defines the core data structures used throughout the application,
particularly the Task dataclass that represents a scheduled task.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Task:
    """Represents a scheduled task in the bot.

    A task can be scheduled to run:
    - Daily at a specific time (hour/minute)
    - On specific days of the week (days_of_week)
    - At fixed intervals (interval_minutes)
    - Once at a specific datetime (run_at)

    Attributes:
        id: Unique identifier assigned by the database. None for unsaved tasks.
        chat_id: Telegram chat ID where the task results will be sent.
        prompt: The text prompt to send to OpenAI.
        hour: Hour of execution (0-23) for daily/weekly tasks.
        minute: Minute of execution (0-59) for daily/weekly tasks.
        timezone: IANA timezone name (e.g., 'UTC', 'Europe/Madrid').
        run_at: Specific datetime for one-time tasks. None for recurring tasks.
        paused: Whether the task is currently paused.
        interval_minutes: Interval in minutes for recurring tasks. None for cron-based.
        name: Optional human-readable name for the task.
        days_of_week: Comma-separated day abbreviations (e.g., 'mon,wed,fri').
    """

    id: Optional[int]
    chat_id: int
    prompt: str
    hour: int
    minute: int
    timezone: str
    run_at: Optional[datetime] = None
    paused: bool = False
    interval_minutes: Optional[int] = None
    name: Optional[str] = None
    days_of_week: Optional[str] = None

    @property
    def job_id(self) -> str:
        """Return the APScheduler job ID for this task.

        Returns:
            String in format 'task-{id}' or empty string if id is None.
        """
        return f"task-{self.id}" if self.id is not None else ""

    @property
    def is_interval(self) -> bool:
        """Check if this is an interval-based task.

        Returns:
            True if the task runs at fixed intervals, False otherwise.
        """
        return self.interval_minutes is not None

    @property
    def display_name(self) -> str:
        """Return a human-readable name for the task.

        Returns:
            The custom name if set, otherwise 'Task #{id}' or 'Task'.
        """
        if self.name:
            return self.name
        return f"Task #{self.id}" if self.id else "Task"
