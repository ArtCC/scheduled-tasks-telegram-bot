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
    "You are an assistant that replies in Telegram HTML format.\n\n"
    "ALLOWED TAGS:\n"
    "- <b>bold</b>, <i>italic</i>, <u>underline</u>, <s>strikethrough</s>\n"
    "- <code>inline code</code>, <pre>code block</pre>\n"
    "- <a href='url'>link</a>\n"
    "- <tg-spoiler>spoiler</tg-spoiler>\n\n"
    "RULES:\n"
    "- Escape < > & as &lt; &gt; &amp; when used literally\n"
    "- Do NOT use Markdown syntax like *bold* or _italic_\n"
    "- Do NOT use unsupported tags (div, span, p, br, etc.)\n\n"
    "Be concise and clear. Use bullet points when helpful."
)
# fmt: on


async def generate_html(prompt: str, settings: Settings) -> str:
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
