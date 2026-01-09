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


def _extract_response_text(response) -> str:
    """Extract text from Responses API output in a robust way."""
    # Try common attributes first
    if hasattr(response, "output_text") and response.output_text:
        if isinstance(response.output_text, str):
            return response.output_text
        if hasattr(response.output_text, "value"):
            return response.output_text.value
        return str(response.output_text)

    if hasattr(response, "output") and response.output:
        for item in response.output:
            if getattr(item, "type", None) == "message":
                for content in getattr(item, "content", []) or []:
                    if getattr(content, "type", None) == "output_text":
                        text = getattr(content, "text", None)
                        if isinstance(text, str):
                            return text
                        if hasattr(text, "value"):
                            return text.value
                        if hasattr(text, "content"):
                            return text.content
                        return str(text)

    # Fallback: check for generic text attribute
    if hasattr(response, "text") and response.text:
        return response.text if isinstance(response.text, str) else str(response.text)

    logger.warning("Could not extract text from response: %s", type(response))
    logger.debug("Response attributes: %s", dir(response))
    return ""


async def generate_html(prompt: str, settings: Settings) -> str:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    now = datetime.now(timezone.utc).isoformat()
    user_input = f"Current time (UTC): {now}. Timezone: {settings.timezone}. Request: {prompt}"

    retryable = (RateLimitError, APIError, APIConnectionError, APITimeoutError)
    delay = 1.0
    last_exc: Exception | None = None

    params = {
        "model": settings.openai_model,
        "instructions": SYSTEM_INSTRUCTION,
        "input": user_input,
        "tools": [{"type": "web_search"}],
        "max_output_tokens": settings.openai_max_tokens,
        "response_format": {"type": "text"},
    }

    if not settings.openai_model.startswith("gpt-5"):
        params["temperature"] = settings.openai_temperature

    for attempt in range(1, settings.openai_max_retries + 1):
        try:
            response = await client.responses.create(**params)
            text = _extract_response_text(response)

            if not text:
                logger.error("Empty response from OpenAI Responses API")
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
