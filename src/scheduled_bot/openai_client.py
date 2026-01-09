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
    "Eres un asistente que responde SIEMPRE en MarkdownV2 apto para Telegram. "
    "Responde de forma concisa y clara, usa listas y tablas compactas cuando tenga sentido. "
    "No incluyas código HTML ni enlaces rotos. Evita texto excesivamente largo."
)


async def generate_markdown(prompt: str, settings: Settings) -> str:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    now = datetime.now(timezone.utc).isoformat()
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {
            "role": "user",
            "content": (
                "Momento de ejecución (UTC): "
                f"{now}. Zona horaria objetivo: {settings.timezone}. "
                "Responde en MarkdownV2 de Telegram. "
                f"Solicitud: {prompt}"
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
    raise RuntimeError("No se pudo generar la respuesta")
