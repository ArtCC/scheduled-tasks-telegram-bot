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
    """Extract text content from Responses API output."""
    try:
        # Try to extract from output items
        if hasattr(response, "output") and response.output:
            for item in response.output:
                if hasattr(item, "type") and item.type == "message":
                    if hasattr(item, "content") and item.content:
                        for content in item.content:
                            if hasattr(content, "type") and content.type == "output_text":
                                if hasattr(content, "text"):
                                    return content.text

        # Alternative: check if response has text directly
        if hasattr(response, "text") and response.text:
            return response.text

        logger.warning("Could not extract text from response: %s", type(response))
        logger.debug("Response attributes: %s", dir(response))
    except Exception as e:
        logger.error("Error extracting response text: %s", e)

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
            text = _extract_response_text(response)

            if not text:
                logger.error("Empty response from OpenAI. Response type: %s", type(response))
                # Fallback message
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
