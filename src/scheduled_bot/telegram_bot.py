from typing import List

from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message

from .formatting import escape_markdown_v2
from .scheduler import BotScheduler

router = Router()

# Global reference set by build_dispatcher
_scheduler: BotScheduler | None = None


def _get_scheduler() -> BotScheduler:
    if not _scheduler:
        raise RuntimeError("Scheduler is not configured")
    return _scheduler


@router.message(Command("start", "help"))
async def handle_start(message: Message) -> None:
    text = (
        "Hi! I'm your scheduled tasks bot.\n\n"
        "Use /add HH:MM [Timezone] your request to receive it daily.\n"
        "Example: /add 08:00 Europe/Madrid Weather summary.\n\n"
        "For a one-time run, use /add YYYY-MM-DDTHH:MM your request (ISO 8601).\n"
        "Commands: /add, /list, /delete <id>."
    )
    await message.answer(escape_markdown_v2(text))


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
        await message.answer("You have no tasks.")
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
        await message.answer("Usage: /delete <id>")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("The id must be numeric")
        return

    removed = scheduler.remove_task(task_id, message.chat.id)
    if removed:
        await message.answer(escape_markdown_v2(f"Task #{task_id} deleted"))
    else:
        await message.answer("Task not found")


def build_dispatcher(scheduler: BotScheduler) -> Dispatcher:
    global _scheduler
    _scheduler = scheduler
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher
