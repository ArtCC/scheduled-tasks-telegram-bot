import logging
import re
from datetime import datetime
from typing import Any, Awaitable, Callable, List

from aiogram import BaseMiddleware, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)

from .formatting import clamp_message, escape_html
from .openai_client import generate_html
from .scheduler import BotScheduler, parse_days, parse_interval

logger = logging.getLogger(__name__)

router = Router()

# Global reference set by build_dispatcher
_scheduler: BotScheduler | None = None


def _get_scheduler() -> BotScheduler:
    if not _scheduler:
        raise RuntimeError("Scheduler is not configured")
    return _scheduler


class AuthMiddleware(BaseMiddleware):
    """Middleware that blocks messages from unauthorized chat IDs."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        scheduler = _get_scheduler()
        if isinstance(event, Message) and event.chat:
            if event.chat.id not in scheduler.settings.allowed_chat_ids:
                logger.warning(
                    "Unauthorized access attempt from chat_id=%s",
                    event.chat.id,
                )
                await event.answer(
                    "⛔ You are not authorized to use this bot.\n\n"
                    f"Your chat ID is: <code>{event.chat.id}</code>\n\n"
                    "If you are the owner, add this ID to ALLOWED_CHAT_IDS.",
                    parse_mode=ParseMode.HTML,
                )
                return None
        return await handler(event, data)


@router.message(Command("start", "help"))
async def handle_start(message: Message) -> None:
    text = (
        "Hi! I'm your scheduled tasks bot.\n\n"
        "<b>Commands:</b>\n"
        "/ask &lt;question&gt; - Ask something right now\n"
        "/add HH:MM [TZ] [days] [--name=X] &lt;request&gt; - Daily task\n"
        "/add YYYY-MM-DDTHH:MM &lt;request&gt; - One-time task\n"
        "/every &lt;interval&gt; &lt;request&gt; - Interval task\n"
        "/list - Show your scheduled tasks\n"
        "/run &lt;id&gt; - Run a task now\n"
        "/edit &lt;id&gt; &lt;new prompt&gt; - Edit a task\n"
        "/pause &lt;id&gt; - Pause a task\n"
        "/resume &lt;id&gt; - Resume a paused task\n"
        "/delete &lt;id&gt; - Remove a task\n"
        "/status - Bot status\n\n"
        "<b>Examples:</b>\n"
        "/add 08:00 Europe/Madrid Weather summary\n"
        "/add 09:00 mon,wed,fri Weekly standup notes\n"
        "/add 08:00 --name=News Daily headlines\n"
        "/every 2h Check server status"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("ask"))
async def handle_ask(message: Message) -> None:
    """Handle direct queries without scheduling."""
    scheduler = _get_scheduler()
    settings = scheduler.settings
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Usage: /ask &lt;your question&gt;")
        return

    prompt = parts[1].strip()

    if len(prompt) > settings.max_prompt_chars:
        await message.answer(f"Question too long. Maximum {settings.max_prompt_chars} characters.")
        return

    # Send typing indicator
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        content = await generate_html(prompt, settings)
        content = clamp_message(content, settings.response_max_chars)

        try:
            await message.answer(content, parse_mode=ParseMode.HTML)
        except TelegramBadRequest as e:
            # Fallback to plain text if HTML parsing fails
            logger.debug("HTML fallback for /ask: %s", e)
            await message.answer(content, parse_mode=None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to process /ask: %s", exc)
        await message.answer(
            "❌ <b>Error</b>\n\n" "Could not process your request. Please try again later.",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("add"))
async def handle_add(message: Message) -> None:
    """
    Handle /add command with flexible syntax:
    /add HH:MM [TZ] [days] [--name=X] <prompt>
    /add YYYY-MM-DDTHH:MM [--name=X] <prompt>
    """
    scheduler = _get_scheduler()
    settings = scheduler.settings
    text = (message.text or "").strip()

    # Extract --name=X if present
    name = None
    name_match = re.search(r"--name=(\S+)", text)
    if name_match:
        name = name_match.group(1)
        text = text.replace(name_match.group(0), "").strip()

    parts = text.split()
    if len(parts) < 3:
        await message.answer(
            "Usage: /add HH:MM [TZ] [days] [--name=X] &lt;prompt&gt;\n"
            "Examples:\n"
            "  /add 08:00 Weather summary\n"
            "  /add 08:00 Europe/Madrid Weather summary\n"
            "  /add 09:00 mon,wed,fri Standup notes\n"
            "  /add 08:00 --name=News Daily headlines"
        )
        return

    time_spec = parts[1]  # HH:MM or ISO datetime
    tz_name = None
    days_of_week = None

    # Parse remaining arguments
    idx = 2
    prompt_parts = []

    while idx < len(parts):
        token = parts[idx]

        # Check if it's a timezone (contains '/')
        if "/" in token and tz_name is None and not days_of_week:
            tz_name = token
            idx += 1
            continue

        # Check if it's days specification (contains comma or is a valid day)
        if days_of_week is None and re.match(r"^[a-z,]+$", token.lower()):
            try:
                days_of_week = parse_days(token)
                idx += 1
                continue
            except ValueError:
                pass  # Not valid days, treat as prompt

        # Rest is the prompt
        prompt_parts = parts[idx:]
        break

    prompt = " ".join(prompt_parts)

    if not prompt:
        await message.answer("Please provide a prompt for the task.")
        return

    if len(prompt) > settings.max_prompt_chars:
        await message.answer(f"Prompt too long. Maximum {settings.max_prompt_chars} characters.")
        return

    try:
        task = await scheduler.add_task(
            message.chat.id, time_spec, prompt, tz_name, name, days_of_week
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to add task: %s", exc)
        await message.answer(
            "❌ <b>Error</b>\n\n" "Could not create the task. Check the format and try again.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Build confirmation message
    task_name = task.display_name
    run_info = task.run_at.isoformat() if task.run_at else f"{task.hour:02d}:{task.minute:02d}"

    if task.run_at:
        msg = f"✅ <b>{escape_html(task_name)}</b> scheduled for {run_info} ({task.timezone})."
    elif task.days_of_week:
        days_display = task.days_of_week.upper()
        msg = (
            f"✅ <b>{escape_html(task_name)}</b> created.\n"
            f"Runs at {run_info} on {days_display} ({task.timezone})"
        )
    else:
        msg = (
            f"✅ <b>{escape_html(task_name)}</b> created.\n"
            f"Runs daily at {run_info} ({task.timezone})"
        )

    await message.answer(msg, parse_mode=ParseMode.HTML)


@router.message(Command("every"))
async def handle_every(message: Message) -> None:
    """Schedule an interval-based task."""
    scheduler = _get_scheduler()
    settings = scheduler.settings
    parts = (message.text or "").split(maxsplit=2)

    if len(parts) < 3:
        await message.answer(
            "Usage: /every &lt;interval&gt; &lt;request&gt;\nExample: /every 2h Check status"
        )
        return

    interval_spec = parts[1]
    prompt = parts[2].strip()

    if len(prompt) > settings.max_prompt_chars:
        await message.answer(f"Prompt too long. Maximum {settings.max_prompt_chars} characters.")
        return

    try:
        interval_minutes = parse_interval(interval_spec)
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return

    try:
        task = await scheduler.add_interval_task(message.chat.id, interval_minutes, prompt)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to add interval task: %s", exc)
        await message.answer(
            "❌ <b>Error</b>\n\n" "Could not create the task. Please try again.",
            parse_mode=ParseMode.HTML,
        )
        return

    interval_str = _format_interval(interval_minutes)
    await message.answer(f"⏱️ Task #{task.id} created. I'll run it {interval_str}.")


@router.message(Command("run"))
async def handle_run(message: Message) -> None:
    """Run a task immediately."""
    scheduler = _get_scheduler()
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        await message.answer("Usage: /run &lt;id&gt;")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("The id must be numeric")
        return

    task = scheduler.storage.get_task(task_id, message.chat.id)
    if not task:
        await message.answer("Task not found")
        return

    await message.answer(f"🚀 Running task #{task_id}...")
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    await scheduler.run_task_now(task_id, message.chat.id)


@router.message(Command("status"))
async def handle_status(message: Message) -> None:
    """Show bot status."""
    scheduler = _get_scheduler()
    status = scheduler.get_status()
    tasks = scheduler.storage.list_tasks(message.chat.id)

    active = sum(1 for t in tasks if not t.paused)
    paused = sum(1 for t in tasks if t.paused)

    # Find next execution time for user's tasks
    next_run = None
    for job_info in status["jobs"]:
        task_id_str = job_info["id"].replace("task-", "")
        try:
            task_id = int(task_id_str)
            task = scheduler.storage.get_task(task_id, message.chat.id)
            if task and not task.paused and job_info["next_run"] != "paused":
                job_next = datetime.fromisoformat(job_info["next_run"])
                if next_run is None or job_next < next_run:
                    next_run = job_next
        except (ValueError, TypeError):
            continue

    lines = [
        "📊 <b>Bot Status</b>\n",
        f"🟢 Scheduler: {'running' if status['running'] else '🔴 stopped'}",
        f"📋 Your tasks: {len(tasks)} ({active} active, {paused} paused)",
    ]

    if next_run:
        lines.append(f"⏰ Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


def _build_task_keyboard(task) -> InlineKeyboardMarkup:
    """Build inline keyboard for a task."""
    task_id = task.id
    if task.paused:
        pause_btn = InlineKeyboardButton(text="▶️ Resume", callback_data=f"resume:{task_id}")
    else:
        pause_btn = InlineKeyboardButton(text="⏸️ Pause", callback_data=f"pause:{task_id}")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️ Run", callback_data=f"run:{task_id}"),
                pause_btn,
                InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete:{task_id}"),
            ]
        ]
    )


def _format_interval(minutes: int) -> str:
    """Format interval minutes as human-readable string."""
    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        if mins:
            return f"every {hours}h{mins}m"
        return f"every {hours}h"
    return f"every {minutes}m"


@router.message(Command("list"))
async def handle_list(message: Message) -> None:
    scheduler = _get_scheduler()
    tasks: List = scheduler.storage.list_tasks(message.chat.id)
    if not tasks:
        await message.answer("You have no tasks.")
        return

    for task in tasks:
        text = _format_task_text(task)
        await message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=_build_task_keyboard(task),
        )


def _format_task_text(task) -> str:
    """Format task for display in /list and callbacks."""
    if task.interval_minutes:
        when = _format_interval(task.interval_minutes)
    elif task.run_at:
        when = task.run_at.isoformat()
    elif task.days_of_week:
        when = f"{task.hour:02d}:{task.minute:02d} ({task.days_of_week.upper()})"
    else:
        when = f"{task.hour:02d}:{task.minute:02d} daily"

    status = "⏸️ " if task.paused else ""
    task_name = task.display_name
    return (
        f"{status}<b>{escape_html(task_name)}</b> (#{task.id}): "
        f"{when} ({task.timezone})\n{escape_html(task.prompt)}"
    )


@router.callback_query(F.data.startswith("pause:"))
async def callback_pause(callback: CallbackQuery) -> None:
    """Handle pause button callback."""
    scheduler = _get_scheduler()
    task_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id

    task = scheduler.storage.get_task(task_id, chat_id)
    if not task:
        await callback.answer("Task not found", show_alert=True)
        return

    scheduler.pause_task(task_id, chat_id)
    await callback.answer("⏸️ Task paused")

    # Update the message with new keyboard
    task.paused = True
    text = _format_task_text(task)
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_build_task_keyboard(task),
    )


@router.callback_query(F.data.startswith("resume:"))
async def callback_resume(callback: CallbackQuery) -> None:
    """Handle resume button callback."""
    scheduler = _get_scheduler()
    task_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id

    task = scheduler.storage.get_task(task_id, chat_id)
    if not task:
        await callback.answer("Task not found", show_alert=True)
        return

    scheduler.resume_task(task_id, chat_id)
    await callback.answer("▶️ Task resumed")

    # Update the message with new keyboard
    task.paused = False
    text = _format_task_text(task)
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_build_task_keyboard(task),
    )


@router.callback_query(F.data.startswith("delete:"))
async def callback_delete(callback: CallbackQuery) -> None:
    """Handle delete button callback."""
    scheduler = _get_scheduler()
    task_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id

    removed = scheduler.remove_task(task_id, chat_id)
    if removed:
        await callback.answer("🗑️ Task deleted")
        await callback.message.delete()
    else:
        await callback.answer("Task not found", show_alert=True)


@router.callback_query(F.data.startswith("run:"))
async def callback_run(callback: CallbackQuery) -> None:
    """Handle run button callback."""
    scheduler = _get_scheduler()
    task_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id

    task = scheduler.storage.get_task(task_id, chat_id)
    if not task:
        await callback.answer("Task not found", show_alert=True)
        return

    await callback.answer(f"🚀 Running task #{task_id}...")
    await callback.message.chat.do(action="typing")
    await scheduler.run_task_now(task_id, chat_id)


@router.message(Command("delete"))
async def handle_delete(message: Message) -> None:
    scheduler = _get_scheduler()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /delete &lt;id&gt;")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("The id must be numeric")
        return

    removed = scheduler.remove_task(task_id, message.chat.id)
    if removed:
        await message.answer(f"Task #{task_id} deleted")
    else:
        await message.answer("Task not found")


@router.message(Command("edit"))
async def handle_edit(message: Message) -> None:
    """Edit the prompt of an existing task."""
    scheduler = _get_scheduler()
    settings = scheduler.settings
    parts = (message.text or "").split(maxsplit=2)

    if len(parts) < 3:
        await message.answer("Usage: /edit &lt;id&gt; &lt;new prompt&gt;")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("The id must be numeric")
        return

    new_prompt = parts[2].strip()
    if not new_prompt:
        await message.answer("The new prompt cannot be empty")
        return

    if len(new_prompt) > settings.max_prompt_chars:
        await message.answer(f"Prompt too long. Maximum {settings.max_prompt_chars} characters.")
        return

    updated = scheduler.storage.update_prompt(task_id, message.chat.id, new_prompt)
    if updated:
        await message.answer(f"✏️ Task #{task_id} updated")
    else:
        await message.answer("Task not found")


@router.message(Command("pause"))
async def handle_pause(message: Message) -> None:
    """Pause a scheduled task."""
    scheduler = _get_scheduler()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /pause &lt;id&gt;")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("The id must be numeric")
        return

    paused = scheduler.pause_task(task_id, message.chat.id)
    if paused:
        await message.answer(f"⏸️ Task #{task_id} paused")
    else:
        await message.answer("Task not found")


@router.message(Command("resume"))
async def handle_resume(message: Message) -> None:
    """Resume a paused task."""
    scheduler = _get_scheduler()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /resume &lt;id&gt;")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("The id must be numeric")
        return

    resumed = scheduler.resume_task(task_id, message.chat.id)
    if resumed:
        await message.answer(f"▶️ Task #{task_id} resumed")
    else:
        await message.answer("Task not found")


def build_dispatcher(scheduler: BotScheduler) -> Dispatcher:
    global _scheduler
    _scheduler = scheduler
    dispatcher = Dispatcher()
    router.message.middleware(AuthMiddleware())
    dispatcher.include_router(router)
    return dispatcher
