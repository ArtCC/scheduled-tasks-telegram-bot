import re

# Characters requiring escape in Telegram MarkdownV2
_MARKDOWN_V2_SPECIALS = re.compile(r"([_\*\[\]\(\)~`>#+\-=|{}.!])")


def escape_markdown_v2(text: str) -> str:
    return _MARKDOWN_V2_SPECIALS.sub(r"\\\1", text)


def clamp_message(text: str, max_chars: int, suffix: str = " …[truncated]") -> str:
    if len(text) <= max_chars:
        return text

    if max_chars <= len(suffix):
        return suffix[:max_chars]

    return text[: max_chars - len(suffix)] + suffix
