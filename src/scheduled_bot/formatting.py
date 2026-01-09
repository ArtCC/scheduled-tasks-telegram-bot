import html


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram.

    Only < > & need to be escaped for Telegram HTML mode.
    """
    return html.escape(text)


def clamp_message(text: str, max_chars: int, suffix: str = " …[truncated]") -> str:
    """Clamp message length ensuring string conversion first."""
    text = str(text)
    if len(text) <= max_chars:
        return text

    if max_chars <= len(suffix):
        return suffix[:max_chars]

    return text[: max_chars - len(suffix)] + suffix
