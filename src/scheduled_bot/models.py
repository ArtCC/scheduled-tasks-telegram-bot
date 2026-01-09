from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Task:
    id: Optional[int]
    chat_id: int
    prompt: str
    hour: int
    minute: int
    timezone: str
    run_at: Optional[datetime] = None
    paused: bool = False
    interval_minutes: Optional[int] = None  # For interval-based tasks (every Xh/Xm)

    @property
    def job_id(self) -> str:
        return f"task-{self.id}" if self.id is not None else ""

    @property
    def is_interval(self) -> bool:
        return self.interval_minutes is not None
