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
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
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


def _main_keyboard() -> ReplyKeyboardMarkup:
    """Build the persistent main keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 My Tasks"), KeyboardButton(text="➕ New Task")],
            [KeyboardButton(text="📊 Status"), KeyboardButton(text="❓ Help")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


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
        "🤖 <b>Scheduled Tasks Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💬 <b>Instant Queries</b>\n"
        "├ /ask &lt;question&gt; — Get an answer now\n\n"
        "📅 <b>Create Tasks</b>\n"
        "├ /add HH:MM [TZ] [days] [--name=X] &lt;prompt&gt;\n"
        "├ /add YYYY-MM-DDTHH:MM &lt;prompt&gt;\n"
        "├ /every &lt;interval&gt; &lt;prompt&gt;\n"
        "└ /remember HH:MM &lt;text&gt; — No AI, plain text\n\n"
        "🔧 <b>Manage Tasks</b>\n"
        "├ /list — View all tasks\n"
        "├ /run &lt;id&gt; — Execute now\n"
        "├ /edit &lt;id&gt; &lt;new prompt&gt;\n"
        "├ /clone &lt;id&gt; — Duplicate a task\n"
        "├ /pause &lt;id&gt; · /resume &lt;id&gt;\n"
        "└ /delete &lt;id&gt;\n\n"
        "📊 <b>Info</b>\n"
        "└ /status — Bot status &amp; next runs\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📝 <b>Examples</b>\n\n"
        "<code>/add 08:00 Daily weather summary</code>\n"
        "<code>/add 09:00 mon,wed,fri --name=Standup Team notes</code>\n"
        "<code>/every 2h Check server status</code>\n"
        "<code>/remember 09:00 Take medication</code>\n"
        "<code>/remember 2026-03-15T10:00 Doctor appointment</code>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=_main_keyboard())


@router.message(F.text == "📋 My Tasks")
async def handle_kb_list(message: Message) -> None:
    await handle_list(message)


@router.message(F.text == "➕ New Task")
async def handle_kb_new_task(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Create a new task</b>\n\n"
        "Choose a command:\n\n"
        "📅 /add HH:MM &lt;prompt&gt; — AI task\n"
        "⏱️ /every &lt;interval&gt; &lt;prompt&gt; — Interval task\n"
        "🔔 /remember HH:MM &lt;text&gt; — Plain reminder",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == "📊 Status")
async def handle_kb_status(message: Message) -> None:
    await handle_status(message)


@router.message(F.text == "❓ Help")
async def handle_kb_help(message: Message) -> None:
    await handle_start(message)


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

    await message.answer(msg, parse_mode=ParseMode.HTML, reply_markup=_main_keyboard())


@router.message(Command("remember"))
async def handle_remember(message: Message) -> None:
    """
    Handle /remember command - simple reminders without OpenAI.
    /remember HH:MM [TZ] [days] <text>
    /remember YYYY-MM-DDTHH:MM <text>
    """
    scheduler = _get_scheduler()
    settings = scheduler.settings
    text = (message.text or "").strip()

    parts = text.split()
    if len(parts) < 3:
        await message.answer(
            "Usage: /remember HH:MM [TZ] [days] &lt;text&gt;\n"
            "Examples:\n"
            "  /remember 09:00 Take medication\n"
            "  /remember 08:00 Europe/Madrid Call mom\n"
            "  /remember 09:00 mon,wed,fri Team meeting\n"
            "  /remember 2026-03-15T10:00 Doctor appointment"
        )
        return

    time_spec = parts[1]
    tz_name = None
    days_of_week = None

    # Parse remaining arguments
    idx = 2
    reminder_parts = []

    while idx < len(parts):
        token = parts[idx]

        # Check if it's a timezone (contains '/')
        if "/" in token and tz_name is None and not days_of_week:
            tz_name = token
            idx += 1
            continue

        # Check if it's days specification
        if days_of_week is None and re.match(r"^[a-z,]+$", token.lower()):
            try:
                days_of_week = parse_days(token)
                idx += 1
                continue
            except ValueError:
                pass

        # Rest is the reminder text
        reminder_parts = parts[idx:]
        break

    reminder_text = " ".join(reminder_parts)

    if not reminder_text:
        await message.answer("Please provide text for the reminder.")
        return

    if len(reminder_text) > settings.max_prompt_chars:
        await message.answer(f"Reminder too long. Maximum {settings.max_prompt_chars} characters.")
        return

    try:
        task = await scheduler.add_task(
            message.chat.id,
            time_spec,
            reminder_text,
            tz_name,
            name=None,
            days_of_week=days_of_week,
            is_reminder=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to add reminder: %s", exc)
        await message.answer(
            "❌ <b>Error</b>\n\n" "Could not create the reminder. Check the format and try again.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Build confirmation message
    run_info = task.run_at.isoformat() if task.run_at else f"{task.hour:02d}:{task.minute:02d}"

    if task.run_at:
        msg = f"🔔 <b>Reminder #{task.id}</b> set for {run_info} ({task.timezone})."
    elif task.days_of_week:
        days_display = task.days_of_week.upper()
        msg = (
            f"🔔 <b>Reminder #{task.id}</b> created.\n"
            f"Will remind you at {run_info} on {days_display} ({task.timezone})"
        )
    else:
        msg = (
            f"🔔 <b>Reminder #{task.id}</b> created.\n"
            f"Will remind you daily at {run_info} ({task.timezone})"
        )

    await message.answer(msg, parse_mode=ParseMode.HTML, reply_markup=_main_keyboard())


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
    await message.answer(
        f"⏱️ Task #{task.id} created. I'll run it {interval_str}.",
        reply_markup=_main_keyboard(),
    )


@router.message(Command("run"))
async def handle_run(message: Message) -> None:
    """Run a task immediately."""
    scheduler = _get_scheduler()
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        await message.answer("ℹ️ Usage: /run &lt;id&gt;\n\nExample: /run 3")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ <b>Invalid ID</b>\n\nThe task ID must be a number.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )
        return

    task = scheduler.storage.get_task(task_id, message.chat.id)
    if not task:
        await message.answer(
            "❌ <b>Task not found</b>\n\nNo task found with that ID.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )
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

    scheduler_status = "🟢 Running" if status["running"] else "🔴 Stopped"

    lines = [
        "📊 <b>Bot Status</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"⚙️ Scheduler: {scheduler_status}",
        f"📋 Tasks: <b>{len(tasks)}</b> total",
        f"   ├ ▶️ Active: {active}",
        f"   └ ⏸️ Paused: {paused}",
    ]

    if next_run:
        lines.append("")
        lines.append(f"⏰ Next run: <code>{next_run.strftime('%Y-%m-%d %H:%M')}</code>")

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
        await message.answer(
            "📋 <b>Your Tasks</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "No tasks yet.\n\n"
            "💡 <i>Use /add, /every or /remember to create one!</i>",
            parse_mode=ParseMode.HTML,
        )
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
    # Determine schedule type and format
    if task.interval_minutes:
        when = _format_interval(task.interval_minutes)
        schedule_icon = "🔄"
    elif task.run_at:
        when = task.run_at.strftime("%Y-%m-%d %H:%M")
        schedule_icon = "📅"
    elif task.days_of_week:
        when = f"{task.hour:02d}:{task.minute:02d} ({task.days_of_week.upper()})"
        schedule_icon = "📆"
    else:
        when = f"{task.hour:02d}:{task.minute:02d} daily"
        schedule_icon = "🕐"

    # Status indicator
    if task.paused:
        status_line = "⏸️ <i>Paused</i>"
    else:
        status_line = "▶️ <i>Active</i>"

    # Type icon
    type_icon = "🔔" if task.is_reminder else "🤖"
    task_name = task.display_name

    # Truncate prompt for display (max 100 chars)
    prompt_display = task.prompt[:100] + "..." if len(task.prompt) > 100 else task.prompt

    return (
        f"{type_icon} <b>{escape_html(task_name)}</b> <code>#{task.id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{schedule_icon} {when} · {task.timezone}\n"
        f"{status_line}\n\n"
        f"📝 {escape_html(prompt_display)}"
    )


@router.callback_query(F.data.startswith("pause:"))
async def callback_pause(callback: CallbackQuery) -> None:
    """Handle pause button callback."""
    scheduler = _get_scheduler()
    task_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id

    task = scheduler.storage.get_task(task_id, chat_id)
    if not task:
        await callback.answer("❌ Task not found", show_alert=True)
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
        await callback.answer("❌ Task not found", show_alert=True)
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
    """Handle delete button - show confirmation."""
    scheduler = _get_scheduler()
    task_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id

    task = scheduler.storage.get_task(task_id, chat_id)
    if not task:
        await callback.answer("❌ Task not found", show_alert=True)
        return

    # Show confirmation keyboard
    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Yes, delete", callback_data=f"confirm_delete:{task_id}"
                ),
                InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_delete:{task_id}"),
            ]
        ]
    )
    await callback.answer()
    await callback.message.edit_text(
        f"⚠️ <b>Delete {task.display_name}?</b>\n\n" f"This action cannot be undone.",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_keyboard,
    )


@router.callback_query(F.data.startswith("confirm_delete:"))
async def callback_confirm_delete(callback: CallbackQuery) -> None:
    """Handle confirmed deletion."""
    scheduler = _get_scheduler()
    task_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id

    removed = scheduler.remove_task(task_id, chat_id)
    if removed:
        await callback.answer("🗑️ Task deleted")
        await callback.message.delete()
        await callback.message.answer(
            "✅ <b>Task deleted.</b>\n\n💡 Use /list to see remaining tasks.",
            parse_mode=ParseMode.HTML,
            reply_markup=_main_keyboard(),
        )
    else:
        await callback.answer("❌ Task not found", show_alert=True)


@router.callback_query(F.data.startswith("cancel_delete:"))
async def callback_cancel_delete(callback: CallbackQuery) -> None:
    """Handle cancelled deletion - restore task view."""
    scheduler = _get_scheduler()
    task_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id

    task = scheduler.storage.get_task(task_id, chat_id)
    if not task:
        await callback.answer("❌ Task not found", show_alert=True)
        return

    await callback.answer("Cancelled")
    text = _format_task_text(task)
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_build_task_keyboard(task),
    )


@router.callback_query(F.data.startswith("run:"))
async def callback_run(callback: CallbackQuery) -> None:
    """Handle run button callback."""
    scheduler = _get_scheduler()
    task_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id

    task = scheduler.storage.get_task(task_id, chat_id)
    if not task:
        await callback.answer("❌ Task not found", show_alert=True)
        return

    await callback.answer(f"🚀 Running task #{task_id}...")
    await callback.message.chat.do(action="typing")
    await scheduler.run_task_now(task_id, chat_id)


@router.message(Command("delete"))
async def handle_delete(message: Message) -> None:
    scheduler = _get_scheduler()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("ℹ️ Usage: /delete &lt;id&gt;\n\nExample: /delete 5")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ <b>Invalid ID</b>\n\nThe task ID must be a number.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )
        return

    task = scheduler.storage.get_task(task_id, message.chat.id)
    if not task:
        await message.answer(
            "❌ <b>Task not found</b>\n\nNo task found with that ID.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )
        return

    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Yes, delete", callback_data=f"confirm_delete:{task_id}"
                ),
                InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_delete:{task_id}"),
            ]
        ]
    )
    await message.answer(
        f"⚠️ <b>Delete {escape_html(task.display_name)}?</b>\n\nThis action cannot be undone.",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_keyboard,
    )


@router.message(Command("edit"))
async def handle_edit(message: Message) -> None:
    """Edit the prompt of an existing task."""
    scheduler = _get_scheduler()
    settings = scheduler.settings
    parts = (message.text or "").split(maxsplit=2)

    if len(parts) < 3:
        await message.answer(
            "ℹ️ Usage: /edit &lt;id&gt; &lt;new prompt&gt;\n\nExample: /edit 3 Daily weather summary"
        )
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ <b>Invalid ID</b>\n\nThe task ID must be a number.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )
        return

    new_prompt = parts[2].strip()
    if not new_prompt:
        await message.answer("❌ The new prompt cannot be empty.")
        return

    if len(new_prompt) > settings.max_prompt_chars:
        await message.answer(f"Prompt too long. Maximum {settings.max_prompt_chars} characters.")
        return

    updated = scheduler.storage.update_prompt(task_id, message.chat.id, new_prompt)
    if updated:
        await message.answer(f"✏️ Task #{task_id} updated.")
    else:
        await message.answer(
            "❌ <b>Task not found</b>\n\nNo task found with that ID.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("clone"))
async def handle_clone(message: Message) -> None:
    """Clone an existing task."""
    scheduler = _get_scheduler()
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        await message.answer("ℹ️ Usage: /clone &lt;id&gt;\n\nExample: /clone 3")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ <b>Invalid ID</b>\n\nThe task ID must be a number.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )
        return

    original = scheduler.storage.get_task(task_id, message.chat.id)
    if not original:
        await message.answer(
            "❌ <b>Task not found</b>\n\nNo task found with that ID.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Create a copy of the task
    from .models import Task

    new_task = Task(
        id=None,
        chat_id=original.chat_id,
        prompt=original.prompt,
        hour=original.hour,
        minute=original.minute,
        timezone=original.timezone,
        run_at=original.run_at,
        paused=False,  # New task starts active
        interval_minutes=original.interval_minutes,
        name=f"{original.name} (copy)" if original.name else None,
        days_of_week=original.days_of_week,
        is_reminder=original.is_reminder,
    )

    new_task = scheduler.storage.add_task(new_task)
    scheduler._schedule_task(new_task)

    await message.answer(
        f"📋 Task cloned!\\n\\n"
        f"Original: <b>#{original.id}</b>\\n"
        f"New: <b>#{new_task.id}</b> ({new_task.display_name})",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("pause"))
async def handle_pause(message: Message) -> None:
    """Pause a scheduled task."""
    scheduler = _get_scheduler()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("ℹ️ Usage: /pause &lt;id&gt;\n\nExample: /pause 3")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ <b>Invalid ID</b>\n\nThe task ID must be a number.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )
        return

    paused = scheduler.pause_task(task_id, message.chat.id)
    if paused:
        await message.answer(f"⏸️ Task #{task_id} paused.")
    else:
        await message.answer(
            "❌ <b>Task not found</b>\n\nNo task found with that ID.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("resume"))
async def handle_resume(message: Message) -> None:
    """Resume a paused task."""
    scheduler = _get_scheduler()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("ℹ️ Usage: /resume &lt;id&gt;\n\nExample: /resume 3")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ <b>Invalid ID</b>\n\nThe task ID must be a number.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )
        return

    resumed = scheduler.resume_task(task_id, message.chat.id)
    if resumed:
        await message.answer(f"▶️ Task #{task_id} resumed.")
    else:
        await message.answer(
            "❌ <b>Task not found</b>\n\nNo task found with that ID.\n💡 Use /list to see your tasks.",
            parse_mode=ParseMode.HTML,
        )


def build_dispatcher(scheduler: BotScheduler) -> Dispatcher:
    global _scheduler
    _scheduler = scheduler
    dispatcher = Dispatcher()
    router.message.middleware(AuthMiddleware())
    dispatcher.include_router(router)
    return dispatcher
