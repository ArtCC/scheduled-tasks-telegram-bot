import asyncio
from datetime import datetime, timezone

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from .config import Settings

# fmt: off
SYSTEM_INSTRUCTION = (
    "You are an assistant that replies in Telegram MarkdownV2 format.\n\n"
    "ESCAPE RULES (CRITICAL):\n"
    "- These chars MUST be escaped with \\ when literal: "
    "_ * [ ] ( ) ~ ` > # + - = | { } . ! \\\n"
    "- In URLs inside [text](url), also escape ) and \\\n"
    "- Inside `code` or ```pre```, only escape ` and \\\n\n"
    "EXAMPLES:\n"
    "- Correct: Hello\\! | 1\\.5 | C\\+\\+ | It\\'s | 10\\-15\n"
    "- Bold: *bold* | Italic: _italic_ | Code: `code`\n"
    "- Link: [Google](https://google\\.com)\n\n"
    "FORBIDDEN: HTML tags, unescaped special chars.\n"
    "Be concise. Use bullet lists when helpful."
)
# fmt: on


async def generate_markdown(prompt: str, settings: Settings) -> str:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    now = datetime.now(timezone.utc).isoformat()
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {
            "role": "user",
            "content": (
                f"Current time (UTC): {now}. Timezone: {settings.timezone}. " f"Request: {prompt}"
            ),
        },
    ]

    retryable = (RateLimitError, APIError, APIConnectionError, APITimeoutError)
    delay = 1.0
    last_exc: Exception | None = None

    for attempt in range(1, settings.openai_max_retries + 1):
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                max_tokens=settings.openai_max_tokens,
                temperature=settings.openai_temperature,
            )
            return response.choices[0].message.content or ""
        except retryable as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt == settings.openai_max_retries:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10)

    if last_exc:
        raise last_exc
    raise RuntimeError("Could not generate response")
