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

    @property
    def job_id(self) -> str:
        return f"task-{self.id}" if self.id is not None else ""
