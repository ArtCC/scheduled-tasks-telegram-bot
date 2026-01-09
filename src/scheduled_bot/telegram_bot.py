from typing import List

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message

from .formatting import escape_markdown_v2
from .scheduler import BotScheduler

router = Router()


def _get_scheduler(message: Message) -> BotScheduler:
    scheduler = message.bot.get("scheduler")
    if not scheduler:
        raise RuntimeError("Scheduler is not configured")
    return scheduler  # type: ignore[return-value]


@router.message(Command("start", "help"))
async def handle_start(message: Message) -> None:
    text = (
        "Hola! Soy tu bot de tareas programadas.\n\n"
        "Usa /add HH:MM [ZonaHoraria] tu solicitud para recibirla cada día.\n"
        "Ejemplo: /add 08:00 Europe/Madrid Resumen del clima.\n\n"
        "Para una ejecución única, usa /add YYYY-MM-DDTHH:MM tu solicitud (ISO 8601).\n"
        "Comandos: /add, /list, /delete <id>."
    )
    await message.answer(escape_markdown_v2(text))


@router.message(Command("add"))
async def handle_add(message: Message) -> None:
    scheduler = _get_scheduler(message)
    settings = scheduler.settings
    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 3:
        await message.answer("Usa: /add HH:MM [ZonaHoraria] tu solicitud")
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
            escape_markdown_v2(
                f"El prompt es muy largo. Máximo {settings.max_prompt_chars} caracteres."
            )
        )
        return

    try:
        task = await scheduler.add_task(message.chat.id, time_spec, prompt, tz_name)
    except Exception as exc:  # noqa: BLE001
        await message.answer(escape_markdown_v2(f"No pude crear la tarea: {exc}"))
        return

    run_info = task.run_at.isoformat() if task.run_at else f"{task.hour:02d}:{task.minute:02d}"
    await message.answer(
        escape_markdown_v2(
            f"Tarea #{task.id} creada. Ejecutaré tu solicitud cada día a {run_info} ({task.timezone})"
            if not task.run_at
            else f"Tarea única programada para {run_info} ({task.timezone})."
        )
    )


@router.message(Command("list"))
async def handle_list(message: Message) -> None:
    scheduler = _get_scheduler(message)
    tasks: List = scheduler.storage.list_tasks(message.chat.id)
    if not tasks:
        await message.answer("No tienes tareas.")
        return

    lines = []
    for task in tasks:
        when = (
            task.run_at.isoformat()
            if task.run_at
            else f"{task.hour:02d}:{task.minute:02d} diario"
        )
        lines.append(f"#{task.id}: {when} ({task.timezone}) -> {task.prompt}")
    await message.answer(escape_markdown_v2("\n".join(lines)))


@router.message(Command("delete"))
async def handle_delete(message: Message) -> None:
    scheduler = _get_scheduler(message)
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usa: /delete <id>")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("El id debe ser numérico")
        return

    removed = scheduler.remove_task(task_id, message.chat.id)
    if removed:
        await message.answer(escape_markdown_v2(f"Tarea #{task_id} eliminada"))
    else:
        await message.answer("No encontré esa tarea")


def build_dispatcher(bot: Bot, scheduler: BotScheduler) -> Dispatcher:
    dispatcher = Dispatcher()
    bot["scheduler"] = scheduler
    dispatcher.include_router(router)
    return dispatcher
