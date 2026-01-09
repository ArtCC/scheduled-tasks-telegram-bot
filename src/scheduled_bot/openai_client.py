import asyncio
import logging
from datetime import datetime, timezone

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from .config import Settings

logger = logging.getLogger(__name__)

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
    "Be concise and clear. Use bullet points when helpful.\n"
    "When providing real-time data from web search, include the source."
)
# fmt: on


async def generate_html(prompt: str, settings: Settings) -> str:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    now = datetime.now(timezone.utc).isoformat()
    user_input = f"Current time (UTC): {now}. Timezone: {settings.timezone}. Request: {prompt}"

    retryable = (RateLimitError, APIError, APIConnectionError, APITimeoutError)
    delay = 1.0
    last_exc: Exception | None = None

    for attempt in range(1, settings.openai_max_retries + 1):
        try:
            # Use Chat Completions with web search tool; model will handle search as needed
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": user_input},
                ],
                tools=[{"type": "web_search"}],
                temperature=(
                    None
                    if settings.openai_model.startswith("gpt-5")
                    else settings.openai_temperature
                ),
                max_tokens=settings.openai_max_tokens,
                response_format={"type": "text"},
            )

            text = response.choices[0].message.content

            if not text:
                logger.error("Empty response from OpenAI chat completion")
                return "Lo siento, no pude generar una respuesta. Por favor, inténtalo de nuevo."

            return text
        except retryable as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt == settings.openai_max_retries:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10)

    if last_exc:
        raise last_exc
    raise RuntimeError("Could not generate response")
