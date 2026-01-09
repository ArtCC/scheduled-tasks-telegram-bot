import logging
from typing import Any, Awaitable, Callable, List

from aiogram import BaseMiddleware, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, TelegramObject

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


@router.message(Command("list"))
async def handle_list(message: Message) -> None:
    scheduler = _get_scheduler()
    tasks: List = scheduler.storage.list_tasks(message.chat.id)
    if not tasks:
        await message.answer("You have no tasks.")
        return

    lines = []
    for task in tasks:
        when = (
            task.run_at.isoformat() if task.run_at else f"{task.hour:02d}:{task.minute:02d} daily"
        )
        status = "⏸️ " if task.paused else ""
        lines.append(
            f"{status}#{task.id}: {when} ({task.timezone}) -&gt; {escape_html(task.prompt)}"
        )
    await message.answer("\n".join(lines))


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
