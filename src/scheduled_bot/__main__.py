import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .config import get_settings
from .scheduler import BotScheduler
from .storage import TaskStorage
from .telegram_bot import build_dispatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Commands shown in the Telegram menu
BOT_COMMANDS = [
    BotCommand(command="start", description="👋 Welcome & help"),
    BotCommand(command="help", description="📖 Show all commands"),
    BotCommand(command="ask", description="💬 Ask something now"),
    BotCommand(command="add", description="📅 Schedule a task"),
    BotCommand(command="every", description="⏱️ Interval task (2h, 30m)"),
    BotCommand(command="remember", description="🔔 Simple reminder"),
    BotCommand(command="list", description="📋 View all tasks"),
    BotCommand(command="run", description="▶️ Execute task now"),
    BotCommand(command="edit", description="✏️ Edit task prompt"),
    BotCommand(command="pause", description="⏸️ Pause a task"),
    BotCommand(command="resume", description="▶️ Resume task"),
    BotCommand(command="delete", description="🗑️ Delete a task"),
    BotCommand(command="status", description="📊 Bot status"),
]


async def main() -> None:
    settings = get_settings()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Set bot commands menu
    await bot.set_my_commands(BOT_COMMANDS)

    storage = TaskStorage(settings.database_path)
    scheduler = BotScheduler(bot=bot, storage=storage, settings=settings)
    scheduler.start()

    dispatcher = build_dispatcher(scheduler)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
