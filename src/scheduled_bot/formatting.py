import re

# Characters requiring escape in Telegram MarkdownV2
# According to Telegram docs: _ * [ ] ( ) ~ ` > # + - = | { } . !
# Also backslash \ must be escaped first
_MARKDOWN_V2_SPECIALS = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def escape_markdown_v2(text: str) -> str:
    """Escape all MarkdownV2 special characters.

    According to Telegram Bot API docs, these characters must be escaped
    with a preceding backslash: _ * [ ] ( ) ~ ` > # + - = | { } . !
    The backslash itself must also be escaped.
    """
    return _MARKDOWN_V2_SPECIALS.sub(r"\\\1", text)


def clamp_message(text: str, max_chars: int, suffix: str = " …[truncated]") -> str:
    if len(text) <= max_chars:
        return text

    if max_chars <= len(suffix):
        return suffix[:max_chars]

    return text[: max_chars - len(suffix)] + suffix
