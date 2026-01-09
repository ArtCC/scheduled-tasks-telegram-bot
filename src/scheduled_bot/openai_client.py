"""OpenAI Responses API client with web search capability."""

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
    "When citing web sources, include the URL as a clickable link."
)
# fmt: on


def _extract_text_from_response(response) -> str:
    """
    Extract text from OpenAI Responses API response.

    Response structure:
    - response.output: array of items
    - Each item can be:
      - type="web_search_call" (search was performed)
      - type="message" with content array
    - message.content[]: array with type="output_text" and "text" field
    """
    texts = []

    for item in response.output:
        # Skip web_search_call items - they don't contain text
        if getattr(item, "type", None) == "web_search_call":
            continue

        # Process message items
        if getattr(item, "type", None) == "message":
            content = getattr(item, "content", None)
            if content:
                for content_item in content:
                    if getattr(content_item, "type", None) == "output_text":
                        text = getattr(content_item, "text", None)
                        if text:
                            texts.append(text)

    return "\n\n".join(texts) if texts else ""


async def generate_html(prompt: str, settings: Settings) -> str:
    """Generate HTML response using OpenAI Responses API with web search."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    now = datetime.now(timezone.utc).isoformat()
    user_input = f"Current time (UTC): {now}. Timezone: {settings.timezone}.\n\n{prompt}"

    retryable = (RateLimitError, APIError, APIConnectionError, APITimeoutError)
    delay = 1.0
    last_exc: Exception | None = None

    # Build request parameters for Responses API
    params: dict = {
        "model": settings.openai_model,
        "input": user_input,
        "instructions": SYSTEM_INSTRUCTION,
        "max_output_tokens": settings.openai_max_tokens,
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
    }

    # Temperature not supported on reasoning models (o1, o3, gpt-5)
    model_lower = settings.openai_model.lower()
    is_reasoning_model = (
        model_lower.startswith("gpt-5")
        or model_lower.startswith("o1")
        or model_lower.startswith("o3")
        or model_lower.startswith("o4")
    )

    if not is_reasoning_model:
        params["temperature"] = settings.openai_temperature

    for attempt in range(1, settings.openai_max_retries + 1):
        try:
            # Use Responses API (client.responses.create)
            response = await client.responses.create(**params)

            logger.debug(
                "Response status: %s, model: %s, output items: %d",
                response.status,
                response.model,
                len(response.output) if response.output else 0,
            )

            # Extract text from response
            text = _extract_text_from_response(response)

            if text:
                return text

            # Log details if no text was extracted
            logger.error(
                "Empty text extracted. Status: %s, Output: %s",
                response.status,
                [{"type": getattr(item, "type", None)} for item in (response.output or [])],
            )
            return "Lo siento, no pude generar una respuesta. Por favor, inténtalo de nuevo."

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
