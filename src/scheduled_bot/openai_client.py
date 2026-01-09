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
    "Be concise and clear. Use bullet points when helpful.\n"
    "When providing real-time data from web search, include the source."
)
# fmt: on


def _extract_response_text(response) -> str:
    """Extract text content from Responses API output."""
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    return content.text
    return ""


async def generate_html(prompt: str, settings: Settings) -> str:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    now = datetime.now(timezone.utc).isoformat()
    user_input = f"Current time (UTC): {now}. Timezone: {settings.timezone}. Request: {prompt}"

    retryable = (RateLimitError, APIError, APIConnectionError, APITimeoutError)
    delay = 1.0
    last_exc: Exception | None = None

    # Prepare parameters, conditionally including temperature
    params = {
        "model": settings.openai_model,
        "instructions": SYSTEM_INSTRUCTION,
        "input": user_input,
        "tools": [{"type": "web_search_preview"}],
        "max_output_tokens": settings.openai_max_tokens,
    }

    # Only add temperature for models that support it (not gpt-5-mini)
    if not settings.openai_model.startswith("gpt-5"):
        params["temperature"] = settings.openai_temperature

    for attempt in range(1, settings.openai_max_retries + 1):
        try:
            # Use Responses API with web search enabled
            response = await client.responses.create(**params)
            return _extract_response_text(response)
        except retryable as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt == settings.openai_max_retries:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10)

    if last_exc:
        raise last_exc
    raise RuntimeError("Could not generate response")
