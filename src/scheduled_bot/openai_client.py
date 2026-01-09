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

SYSTEM_INSTRUCTION = (
    "You are an assistant that replies in Telegram MarkdownV2 format.\n\n"
    "CRITICAL MarkdownV2 RULES:\n"
    "1. These characters MUST be escaped with backslash when used literally "
    "(not as formatting): _ * [ ] ( ) ~ ` > # + - = | { } . !\n"
    '2. Example escapes: "Hello\\!" not "Hello!", "1\\.5" not "1.5", '
    '"C\\+\\+" not "C++"\n'
    "3. Bold: *text*, Italic: _text_, Code: `code`, Link: [text](url)\n"
    "4. For URLs, escape ) inside the URL part\n"
    "5. Do NOT use HTML tags\n\n"
    "Be concise and clear. Use lists when appropriate."
)


async def generate_markdown(prompt: str, settings: Settings) -> str:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    now = datetime.now(timezone.utc).isoformat()
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {
            "role": "user",
            "content": (
                f"Current time (UTC): {now}. Timezone: {settings.timezone}. "
                f"Request: {prompt}"
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
