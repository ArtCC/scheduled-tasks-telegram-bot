"""Text formatting utilities for Telegram messages.

This module provides functions for escaping HTML and managing message length
to ensure compatibility with Telegram's message format requirements.
"""

import html


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram.

    Only < > & need to be escaped for Telegram HTML mode.
    Quotes are also escaped for safety.

    Args:
        text: The text to escape.

    Returns:
        Text with HTML special characters escaped.
    """
    return html.escape(text)


def clamp_message(text: str, max_chars: int, suffix: str = " …[truncated]") -> str:
    """Truncate message to a maximum length with a suffix.

    If the message exceeds max_chars, it will be truncated and the suffix
    appended. The total length will not exceed max_chars.

    Args:
        text: The text to clamp. Will be converted to string if not already.
        max_chars: Maximum total length including suffix.
        suffix: Text to append when truncating. Defaults to ' …[truncated]'.

    Returns:
        Original text if within limit, otherwise truncated text with suffix.
    """
    text = str(text)
    if len(text) <= max_chars:
        return text

    if max_chars <= len(suffix):
        return suffix[:max_chars]

    return text[: max_chars - len(suffix)] + suffix
