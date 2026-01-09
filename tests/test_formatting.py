"""Tests for scheduled_bot.formatting module."""

from scheduled_bot.formatting import clamp_message, escape_html


class TestEscapeHtml:
    """Tests for escape_html function."""

    def test_escape_html_special_chars(self):
        """Test escaping HTML special characters."""
        text = "Special <characters> need & escaping"
        escaped = escape_html(text)
        assert escaped == "Special &lt;characters&gt; need &amp; escaping"

    def test_escape_html_no_special_chars(self):
        """Test that text without special chars is unchanged."""
        text = "Plain text without special chars"
        assert escape_html(text) == text

    def test_escape_html_all_special_chars(self):
        """Test escaping all special characters."""
        text = "<>&"
        assert escape_html(text) == "&lt;&gt;&amp;"

    def test_escape_html_quotes(self):
        """Test that quotes are also escaped."""
        text = "Text with \"quotes\" and 'apostrophes'"
        escaped = escape_html(text)
        assert "&quot;" in escaped or '"' not in escaped

    def test_escape_html_empty_string(self):
        """Test escaping empty string."""
        assert escape_html("") == ""

    def test_escape_html_unicode(self):
        """Test that unicode characters are preserved."""
        text = "Emoji 🚀 and ñ accents"
        assert escape_html(text) == text


class TestClampMessage:
    """Tests for clamp_message function."""

    def test_clamp_message_short(self):
        """Test that short messages are unchanged."""
        text = "Short message"
        assert clamp_message(text, 100) == text

    def test_clamp_message_exact_length(self):
        """Test message exactly at max length."""
        text = "12345"
        assert clamp_message(text, 5) == text

    def test_clamp_message_truncates(self):
        """Test that long messages are truncated."""
        text = "This is a very long message that needs truncation"
        result = clamp_message(text, 20)
        assert len(result) == 20
        assert result.endswith("…[truncated]")

    def test_clamp_message_custom_suffix(self):
        """Test truncation with custom suffix."""
        text = "A long message here"
        result = clamp_message(text, 15, suffix="...")
        assert result.endswith("...")
        assert len(result) == 15

    def test_clamp_message_very_short_max(self):
        """Test truncation when max_chars is very short."""
        text = "Hello world"
        result = clamp_message(text, 5, suffix="...")
        assert len(result) == 5

    def test_clamp_message_converts_to_string(self):
        """Test that non-string input is converted."""
        result = clamp_message(12345, 10)
        assert result == "12345"

    def test_clamp_message_empty(self):
        """Test clamping empty string."""
        assert clamp_message("", 100) == ""
