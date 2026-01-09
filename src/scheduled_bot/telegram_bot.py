import logging
from typing import Any, Awaitable, Callable, List

from aiogram import BaseMiddleware, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, TelegramObject

from .formatting import clamp_message, escape_markdown_v2
from .openai_client import generate_markdown
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
                # Silently ignore unauthorized users
                return None
        return await handler(event, data)


@router.message(Command("start", "help"))
async def handle_start(message: Message) -> None:
    text = (
        "Hi! I'm your scheduled tasks bot.\n\n"
        "Commands:\n"
        "/ask <question> - Ask something right now\n"
        "/add HH:MM [TZ] <request> - Schedule daily task\n"
        "/add YYYY-MM-DDTHH:MM <request> - One-time task\n"
        "/list - Show your scheduled tasks\n"
        "/delete <id> - Remove a task\n\n"
        "Example: /add 08:00 Europe/Madrid Weather summary"
    )
    await message.answer(escape_markdown_v2(text))


@router.message(Command("ask"))
async def handle_ask(message: Message) -> None:
    """Handle direct queries without scheduling."""
    scheduler = _get_scheduler()
    settings = scheduler.settings
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await message.answer(escape_markdown_v2("Usage: /ask <your question>"))
        return

    prompt = parts[1].strip()

    if len(prompt) > settings.max_prompt_chars:
        await message.answer(
            escape_markdown_v2(
                f"Question too long. Maximum {settings.max_prompt_chars} characters."
            )
        )
        return

    # Send typing indicator
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        content = await generate_markdown(prompt, settings)
        content = clamp_message(content, settings.response_max_chars)

        try:
            await message.answer(content, parse_mode=ParseMode.MARKDOWN_V2)
        except TelegramBadRequest:
            # Fallback to plain text if MarkdownV2 parsing fails
            logger.warning("MarkdownV2 parse error for /ask. Sending as plain text.")
            await message.answer(content, parse_mode=None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to process /ask: %s", exc)
        await message.answer(escape_markdown_v2(f"Error: {exc}"))


@router.message(Command("add"))
async def handle_add(message: Message) -> None:
    scheduler = _get_scheduler()
    settings = scheduler.settings
    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 3:
        await message.answer(escape_markdown_v2("Usage: /add HH:MM [Timezone] your request"))
        return

    time_spec = parts[1]
    if len(parts) == 3:
        tz_name = None
        prompt = parts[2]
    else:
        tz_name = parts[2]
        prompt = parts[3]

    if len(prompt) > settings.max_prompt_chars:
        await message.answer(
            escape_markdown_v2(f"Prompt too long. Maximum {settings.max_prompt_chars} characters.")
        )
        return

    try:
        task = await scheduler.add_task(message.chat.id, time_spec, prompt, tz_name)
    except Exception as exc:  # noqa: BLE001
        await message.answer(escape_markdown_v2(f"Could not create task: {exc}"))
        return

    run_info = task.run_at.isoformat() if task.run_at else f"{task.hour:02d}:{task.minute:02d}"
    await message.answer(
        escape_markdown_v2(
            (
                f"Task #{task.id} created. I'll run your request daily at {run_info} "
                f"({task.timezone})"
            )
            if not task.run_at
            else f"One-time task scheduled for {run_info} ({task.timezone})."
        )
    )


@router.message(Command("list"))
async def handle_list(message: Message) -> None:
    scheduler = _get_scheduler()
    tasks: List = scheduler.storage.list_tasks(message.chat.id)
    if not tasks:
        await message.answer(escape_markdown_v2("You have no tasks."))
        return

    lines = []
    for task in tasks:
        when = (
            task.run_at.isoformat() if task.run_at else f"{task.hour:02d}:{task.minute:02d} daily"
        )
        lines.append(f"#{task.id}: {when} ({task.timezone}) -> {task.prompt}")
    await message.answer(escape_markdown_v2("\n".join(lines)))


@router.message(Command("delete"))
async def handle_delete(message: Message) -> None:
    scheduler = _get_scheduler()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(escape_markdown_v2("Usage: /delete <id>"))
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer(escape_markdown_v2("The id must be numeric"))
        return

    removed = scheduler.remove_task(task_id, message.chat.id)
    if removed:
        await message.answer(escape_markdown_v2(f"Task #{task_id} deleted"))
    else:
        await message.answer(escape_markdown_v2("Task not found"))


def build_dispatcher(scheduler: BotScheduler) -> Dispatcher:
    global _scheduler
    _scheduler = scheduler
    dispatcher = Dispatcher()
    router.message.middleware(AuthMiddleware())
    dispatcher.include_router(router)
    return dispatcher
