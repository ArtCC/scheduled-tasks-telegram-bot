from scheduled_bot.formatting import escape_html


def test_escape_html():
    text = "Special <characters> need & escaping"
    escaped = escape_html(text)
    assert escaped == "Special &lt;characters&gt; need &amp; escaping"
