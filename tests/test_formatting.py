from scheduled_bot.formatting import escape_markdown_v2


def test_escape_markdown_v2():
    text = "Special _characters_ need *escaping*"
    escaped = escape_markdown_v2(text)
    assert escaped == r"Special \_characters\_ need \*escaping\*"
