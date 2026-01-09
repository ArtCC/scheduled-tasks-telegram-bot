import logging
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
from .scheduler import BotScheduler

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
        "Commands:\n"
        "/ask &lt;question&gt; - Ask something right now\n"
        "/add HH:MM [TZ] &lt;request&gt; - Schedule daily task\n"
        "/add YYYY-MM-DDTHH:MM &lt;request&gt; - One-time task\n"
        "/list - Show your scheduled tasks\n"
        "/edit &lt;id&gt; &lt;new prompt&gt; - Edit a task\n"
        "/pause &lt;id&gt; - Pause a task\n"
        "/resume &lt;id&gt; - Resume a paused task\n"
        "/delete &lt;id&gt; - Remove a task\n\n"
        "Example: /add 08:00 Europe/Madrid Weather summary"
    )
    await message.answer(text)


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
    scheduler = _get_scheduler()
    settings = scheduler.settings
    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 3:
        await message.answer("Usage: /add HH:MM [Timezone] your request")
        return

    time_spec = parts[1]
    if len(parts) == 3:
        tz_name = None
        prompt = parts[2]
    else:
        tz_name = parts[2]
        prompt = parts[3]

    if len(prompt) > settings.max_prompt_chars:
        await message.answer(f"Prompt too long. Maximum {settings.max_prompt_chars} characters.")
        return

    try:
        task = await scheduler.add_task(message.chat.id, time_spec, prompt, tz_name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to add task: %s", exc)
        await message.answer(
            "❌ <b>Error</b>\n\n" "Could not create the task. Check the format and try again.",
            parse_mode=ParseMode.HTML,
        )
        return

    run_info = task.run_at.isoformat() if task.run_at else f"{task.hour:02d}:{task.minute:02d}"
    if not task.run_at:
        msg = (
            f"Task #{task.id} created. I'll run your request daily at {run_info} "
            f"({task.timezone})"
        )
    else:
        msg = f"One-time task scheduled for {run_info} ({task.timezone})."
    await message.answer(msg)


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
                pause_btn,
                InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete:{task_id}"),
            ]
        ]
    )


@router.message(Command("list"))
async def handle_list(message: Message) -> None:
    scheduler = _get_scheduler()
    tasks: List = scheduler.storage.list_tasks(message.chat.id)
    if not tasks:
        await message.answer("You have no tasks.")
        return

    for task in tasks:
        when = (
            task.run_at.isoformat() if task.run_at else f"{task.hour:02d}:{task.minute:02d} daily"
        )
        status = "⏸️ " if task.paused else ""
        text = f"{status}<b>#{task.id}</b>: {when} ({task.timezone})\n{escape_html(task.prompt)}"
        await message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=_build_task_keyboard(task),
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
    when = task.run_at.isoformat() if task.run_at else f"{task.hour:02d}:{task.minute:02d} daily"
    text = f"⏸️ <b>#{task.id}</b>: {when} ({task.timezone})\n{escape_html(task.prompt)}"
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
    when = task.run_at.isoformat() if task.run_at else f"{task.hour:02d}:{task.minute:02d} daily"
    text = f"<b>#{task.id}</b>: {when} ({task.timezone})\n{escape_html(task.prompt)}"
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
