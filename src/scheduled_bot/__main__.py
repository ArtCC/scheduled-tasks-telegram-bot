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
    BotCommand(command="start", description="Show welcome message and help"),
    BotCommand(command="help", description="Show available commands"),
    BotCommand(command="ask", description="Ask something right now"),
    BotCommand(command="add", description="Schedule a new task"),
    BotCommand(command="list", description="List your scheduled tasks"),
    BotCommand(command="delete", description="Delete a task by ID"),
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
