import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Settings:
    bot_token: str
    openai_api_key: str
    openai_model: str = "gpt-4.1-mini"
    timezone: str = "UTC"
    database_path: str = "./data/bot.db"
    openai_max_tokens: int = 400
    openai_temperature: float = 0.4
    max_prompt_chars: int = 1200
    response_max_chars: int = 3500
    openai_max_retries: int = 3


def _ensure_data_dir(db_path: str) -> None:
    Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings(env_file: Optional[str] = None) -> Settings:
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()

    bot_token = os.getenv("BOT_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not bot_token or not openai_api_key:
        raise RuntimeError("BOT_TOKEN and OPENAI_API_KEY must be set")

    database_path = os.getenv("DATABASE_PATH", Settings.database_path)
    _ensure_data_dir(database_path)

    return Settings(
        bot_token=bot_token,
        openai_api_key=openai_api_key,
        openai_model=os.getenv("OPENAI_MODEL", Settings.openai_model),
        timezone=os.getenv("TIMEZONE", Settings.timezone),
        database_path=database_path,
        openai_max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", Settings.openai_max_tokens)),
        openai_temperature=float(os.getenv("OPENAI_TEMPERATURE", Settings.openai_temperature)),
        max_prompt_chars=int(os.getenv("MAX_PROMPT_CHARS", Settings.max_prompt_chars)),
        response_max_chars=int(os.getenv("MAX_RESPONSE_CHARS", Settings.response_max_chars)),
        openai_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", Settings.openai_max_retries)),
    )
