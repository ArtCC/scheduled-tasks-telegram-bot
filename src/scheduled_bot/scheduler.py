import logging
from datetime import datetime
from typing import Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from .config import Settings
from .formatting import clamp_message, escape_markdown_v2
from .models import Task
from .openai_client import generate_markdown
from .storage import TaskStorage

logger = logging.getLogger(__name__)


class BotScheduler:
    def __init__(self, bot: Bot, storage: TaskStorage, settings: Settings) -> None:
        self.bot = bot
        self.storage = storage
        self.settings = settings
        self.scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.timezone))

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        self._reload_tasks()

    def _reload_tasks(self) -> None:
        for task in self.storage.load_all():
            self._schedule_task(task)

    def _schedule_task(self, task: Task) -> None:
        if task.id is None:
            raise ValueError("Task must have an id before scheduling")

        job_id = task.job_id

        if task.run_at:
            trigger = DateTrigger(run_date=task.run_at.astimezone(ZoneInfo(task.timezone)))
        else:
            trigger = CronTrigger(
                hour=task.hour, minute=task.minute, timezone=ZoneInfo(task.timezone)
            )

        self.scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            args=[task],
            id=job_id,
            replace_existing=True,
        )
        logger.info("Scheduled task %s for chat %s", job_id, task.chat_id)

    async def add_task(
        self, chat_id: int, time_spec: str, prompt: str, timezone_name: str | None = None
    ) -> Task:
        tz_name = timezone_name or self.settings.timezone
        task_time = parse_time_spec(time_spec, tz_name)
        task = Task(
            id=None,
            chat_id=chat_id,
            prompt=prompt,
            hour=task_time[0],
            minute=task_time[1],
            timezone=task_time[3],
            run_at=task_time[2],
        )
        task = self.storage.add_task(task)
        self._schedule_task(task)
        return task

    def remove_task(self, task_id: int, chat_id: int) -> bool:
        removed = self.storage.delete_task(task_id, chat_id)
        job_id = f"task-{task_id}"
        if removed:
            try:
                self.scheduler.remove_job(job_id)
            except Exception:  # noqa: BLE001
                logger.debug("Job %s was not found in scheduler", job_id)
        return removed

    async def _execute_task(self, task: Task) -> None:
        try:
            content = await generate_markdown(task.prompt, self.settings)
            content = clamp_message(content, self.settings.response_max_chars)
            escaped = escape_markdown_v2(content)
            escaped = clamp_message(escaped, self.settings.response_max_chars)
            await self.bot.send_message(
                chat_id=task.chat_id,
                text=escaped,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to execute task %s: %s", task.id, exc)
            await self._notify_failure(task, exc)
        finally:
            if task.run_at:
                self.remove_task(task.id or 0, task.chat_id)

    async def _notify_failure(self, task: Task, exc: Exception) -> None:
        msg = f"No se pudo generar la respuesta: {exc}"
        await self.bot.send_message(
            chat_id=task.chat_id,
            text=escape_markdown_v2(msg),
            parse_mode=ParseMode.MARKDOWN_V2,
        )


def parse_time_spec(time_spec: str, timezone_name: str) -> Tuple[int, int, datetime | None, str]:
    cleaned = time_spec.strip()
    target_tz = _get_zoneinfo(timezone_name)

    if "T" in cleaned or "-" in cleaned:
        normalized = cleaned.replace("Z", "+00:00")
        run_at = datetime.fromisoformat(normalized)
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=target_tz)
        run_at = run_at.astimezone(target_tz)
        return run_at.hour, run_at.minute, run_at, timezone_name

    parts = cleaned.split(":")
    if len(parts) != 2:
        raise ValueError("Invalid time format. Use HH:MM or ISO 8601.")
    hour, minute = int(parts[0]), int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Hour or minute out of range")
    return hour, minute, None, timezone_name


def _get_zoneinfo(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            "Invalid timezone. Use an IANA TZ, e.g. UTC, Europe/Madrid, America/New_York."
        ) from exc
