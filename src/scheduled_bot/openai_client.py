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
    """Extract text from Responses API output.

    According to OpenAI docs, the response structure is:
    - response.output_text (SDK convenience property)
    - response.output[].content[].text (where type == "output_text")
    """
    # Method 1: SDK convenience property (Python/JS SDKs)
    if hasattr(response, "output_text") and response.output_text:
        return str(response.output_text)

    # Method 2: Parse output array structure
    if hasattr(response, "output") and response.output:
        for item in response.output:
            item_type = getattr(item, "type", None)
            if item_type == "message":
                content_list = getattr(item, "content", None) or []
                for content in content_list:
                    content_type = getattr(content, "type", None)
                    if content_type == "output_text":
                        text = getattr(content, "text", "")
                        if text:
                            return str(text)

    logger.warning(
        "Could not extract text. Response type: %s, has output_text: %s",
        type(response).__name__,
        hasattr(response, "output_text"),
    )
    return ""


async def generate_html(prompt: str, settings: Settings) -> str:
    """Generate HTML response using OpenAI Responses API with web search."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    now = datetime.now(timezone.utc).isoformat()
    user_input = f"Current time (UTC): {now}. Timezone: {settings.timezone}. Request: {prompt}"

    retryable = (RateLimitError, APIError, APIConnectionError, APITimeoutError)
    delay = 1.0
    last_exc: Exception | None = None

    # Build request parameters
    # See: https://platform.openai.com/docs/api-reference/responses/create
    params: dict = {
        "model": settings.openai_model,
        "instructions": SYSTEM_INSTRUCTION,
        "input": user_input,
        "tools": [{"type": "web_search"}],
        "max_output_tokens": settings.openai_max_tokens,
    }

    # Temperature not supported on gpt-5 models
    if not settings.openai_model.startswith("gpt-5"):
        params["temperature"] = settings.openai_temperature

    for attempt in range(1, settings.openai_max_retries + 1):
        try:
            response = await client.responses.create(**params)

            # Log response status for debugging
            status = getattr(response, "status", "unknown")
            logger.debug("OpenAI response status: %s", status)

            text = _extract_response_text(response)

            if not text:
                logger.error(
                    "Empty response from OpenAI. Status: %s, Model: %s",
                    status,
                    settings.openai_model,
                )
                return "Lo siento, no pude generar una respuesta. Por favor, inténtalo de nuevo."

            return text

        except retryable as exc:  # type: ignore[misc]
            last_exc = exc
            logger.warning("Retryable error (attempt %d): %s", attempt, exc)
            if attempt == settings.openai_max_retries:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10)

    if last_exc:
        raise last_exc
    raise RuntimeError("Could not generate response")
