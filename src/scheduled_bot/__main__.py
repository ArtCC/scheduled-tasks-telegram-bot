import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from .config import get_settings
from .scheduler import BotScheduler
from .storage import TaskStorage
from .telegram_bot import build_dispatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main() -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token, parse_mode=ParseMode.MARKDOWN_V2)
    storage = TaskStorage(settings.database_path)
    scheduler = BotScheduler(bot=bot, storage=storage, settings=settings)
    scheduler.start()

    dispatcher = build_dispatcher(bot, scheduler)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
