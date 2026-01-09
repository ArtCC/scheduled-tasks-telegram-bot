import logging
import re
from datetime import datetime
from typing import Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import Settings
from .formatting import clamp_message, escape_html
from .models import Task
from .openai_client import generate_html
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
            if task.paused:
                try:
                    self.scheduler.pause_job(task.job_id)
                except Exception:  # noqa: BLE001
                    pass

    def _schedule_task(self, task: Task) -> None:
        if task.id is None:
            raise ValueError("Task must have an id before scheduling")

        job_id = task.job_id

        if task.run_at:
            trigger = DateTrigger(run_date=task.run_at.astimezone(ZoneInfo(task.timezone)))
        elif task.interval_minutes:
            trigger = IntervalTrigger(minutes=task.interval_minutes)
        else:
            # Build CronTrigger with optional days_of_week
            cron_kwargs = {
                "hour": task.hour,
                "minute": task.minute,
                "timezone": ZoneInfo(task.timezone),
            }
            if task.days_of_week:
                cron_kwargs["day_of_week"] = task.days_of_week
            trigger = CronTrigger(**cron_kwargs)

        self.scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            args=[task],
            id=job_id,
            replace_existing=True,
        )
        logger.info("Scheduled task %s for chat %s", job_id, task.chat_id)

    async def add_task(
        self,
        chat_id: int,
        time_spec: str,
        prompt: str,
        timezone_name: str | None = None,
        name: str | None = None,
        days_of_week: str | None = None,
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
            name=name,
            days_of_week=days_of_week,
        )
        task = self.storage.add_task(task)
        self._schedule_task(task)
        return task

    async def add_interval_task(self, chat_id: int, interval_minutes: int, prompt: str) -> Task:
        """Add a task that runs at a fixed interval."""
        task = Task(
            id=None,
            chat_id=chat_id,
            prompt=prompt,
            hour=0,
            minute=0,
            timezone=self.settings.timezone,
            interval_minutes=interval_minutes,
        )
        task = self.storage.add_task(task)
        self._schedule_task(task)
        return task

    async def run_task_now(self, task_id: int, chat_id: int) -> bool:
        """Execute a task immediately. Returns True if task was found."""
        task = self.storage.get_task(task_id, chat_id)
        if not task:
            return False
        await self._execute_task(task, manual=True)
        return True

    def get_status(self) -> dict:
        """Get scheduler status information."""
        jobs = self.scheduler.get_jobs()
        active_jobs = []
        for job in jobs:
            next_run = job.next_run_time
            active_jobs.append(
                {
                    "id": job.id,
                    "next_run": next_run.isoformat() if next_run else "paused",
                }
            )
        return {
            "running": self.scheduler.running,
            "job_count": len(jobs),
            "jobs": active_jobs,
        }

    def remove_task(self, task_id: int, chat_id: int) -> bool:
        removed = self.storage.delete_task(task_id, chat_id)
        job_id = f"task-{task_id}"
        if removed:
            try:
                self.scheduler.remove_job(job_id)
            except Exception:  # noqa: BLE001
                logger.debug("Job %s was not found in scheduler", job_id)
        return removed

    def pause_task(self, task_id: int, chat_id: int) -> bool:
        """Pause a task. Returns True if successful."""
        task = self.storage.get_task(task_id, chat_id)
        if not task:
            return False
        if task.paused:
            return True  # Already paused

        updated = self.storage.set_paused(task_id, chat_id, True)
        if updated:
            job_id = f"task-{task_id}"
            try:
                self.scheduler.pause_job(job_id)
            except Exception:  # noqa: BLE001
                logger.debug("Job %s was not found in scheduler", job_id)
        return updated

    def resume_task(self, task_id: int, chat_id: int) -> bool:
        """Resume a paused task. Returns True if successful."""
        task = self.storage.get_task(task_id, chat_id)
        if not task:
            return False
        if not task.paused:
            return True  # Already running

        updated = self.storage.set_paused(task_id, chat_id, False)
        if updated:
            job_id = f"task-{task_id}"
            try:
                self.scheduler.resume_job(job_id)
            except Exception:  # noqa: BLE001
                logger.debug("Job %s was not found in scheduler", job_id)
        return updated

    async def _execute_task(self, task: Task, manual: bool = False) -> None:
        # Refresh task state to check if paused (skip check for manual runs)
        if not manual:
            current_task = self.storage.get_task(task.id or 0, task.chat_id)
            if current_task and current_task.paused:
                logger.info("Task %s is paused, skipping execution", task.id)
                return

        try:
            # OpenAI is instructed to return HTML-formatted text,
            # so we do NOT escape it here (escaping would break the formatting).
            content = await generate_html(task.prompt, self.settings)
            content = clamp_message(content, self.settings.response_max_chars)

            try:
                await self.bot.send_message(
                    chat_id=task.chat_id,
                    text=content,
                    parse_mode=ParseMode.HTML,
                )
            except TelegramBadRequest as html_err:
                # LLMs may produce invalid HTML; fallback to plain text
                logger.debug("HTML fallback for task %s: %s", task.id, html_err)
                await self.bot.send_message(
                    chat_id=task.chat_id,
                    text=content,
                    parse_mode=None,
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to execute task %s: %s", task.id, exc)
            await self._notify_failure(task, exc)
        finally:
            # Only remove one-time tasks (not interval or manual runs)
            if task.run_at and not manual:
                self.remove_task(task.id or 0, task.chat_id)

    async def _notify_failure(self, task: Task, exc: Exception) -> None:
        msg = f"Failed to generate response: {escape_html(str(exc))}"
        await self.bot.send_message(
            chat_id=task.chat_id,
            text=msg,
            parse_mode=ParseMode.HTML,
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


def parse_interval(interval_spec: str) -> int:
    """
    Parse interval specification like '2h', '30m', '1h30m'.
    Returns total minutes.
    """
    cleaned = interval_spec.strip().lower()
    pattern = r"^(?:(\d+)h)?(?:(\d+)m)?$"
    match = re.match(pattern, cleaned)

    if not match or (not match.group(1) and not match.group(2)):
        raise ValueError("Invalid interval format. Use Xh, Xm, or XhYm (e.g., 2h, 30m, 1h30m)")

    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0

    total_minutes = hours * 60 + minutes
    if total_minutes < 1:
        raise ValueError("Interval must be at least 1 minute")
    if total_minutes > 24 * 60:
        raise ValueError("Interval cannot exceed 24 hours")

    return total_minutes


# Valid day abbreviations for APScheduler
VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def parse_days(days_spec: str) -> str:
    """
    Parse and validate days specification like 'mon,wed,fri'.
    Returns normalized string for APScheduler CronTrigger.
    """
    cleaned = days_spec.strip().lower()
    days = [d.strip() for d in cleaned.split(",")]

    for day in days:
        if day not in VALID_DAYS:
            raise ValueError(f"Invalid day '{day}'. Use: mon, tue, wed, thu, fri, sat, sun")

    return ",".join(days)


def _get_zoneinfo(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            "Invalid timezone. Use an IANA TZ, e.g. UTC, Europe/Madrid, America/New_York."
        ) from exc
