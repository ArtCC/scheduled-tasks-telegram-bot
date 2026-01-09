"""Tests for scheduled_bot.scheduler module."""

from datetime import datetime

import pytest

from scheduled_bot.scheduler import parse_days, parse_interval, parse_time_spec


class TestParseTimeSpec:
    """Tests for parse_time_spec function."""

    def test_parse_time_spec_daily(self):
        """Test parsing daily time format HH:MM."""
        hour, minute, run_at, tz = parse_time_spec("08:30", "UTC")
        assert (hour, minute) == (8, 30)
        assert run_at is None
        assert tz == "UTC"

    def test_parse_time_spec_once(self):
        """Test parsing one-time ISO datetime."""
        hour, minute, run_at, tz = parse_time_spec("2025-12-31T23:59", "UTC")
        assert (hour, minute) == (23, 59)
        assert isinstance(run_at, datetime)
        assert tz == "UTC"

    def test_parse_time_spec_with_timezone_override(self):
        """Test parsing with custom timezone."""
        hour, minute, run_at, tz = parse_time_spec("07:15", "Europe/Madrid")
        assert (hour, minute) == (7, 15)
        assert run_at is None
        assert tz == "Europe/Madrid"

    def test_parse_time_spec_invalid_timezone(self):
        """Test that invalid timezone raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_time_spec("08:00", "Invalid/Zone")
        assert "Invalid timezone" in str(err.value)

    def test_parse_time_spec_once_with_zulu(self):
        """Test parsing ISO datetime with Z suffix."""
        hour, minute, run_at, tz = parse_time_spec("2025-12-31T23:59Z", "UTC")
        assert (hour, minute) == (23, 59)
        assert isinstance(run_at, datetime)
        assert run_at.tzinfo is not None
        assert tz == "UTC"

    def test_parse_time_spec_invalid_format(self):
        """Test that invalid time format raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_time_spec("invalid", "UTC")
        assert "Invalid time format" in str(err.value)

    def test_parse_time_spec_hour_out_of_range(self):
        """Test that hour > 23 raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_time_spec("25:00", "UTC")
        assert "out of range" in str(err.value)

    def test_parse_time_spec_minute_out_of_range(self):
        """Test that minute > 59 raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_time_spec("08:60", "UTC")
        assert "out of range" in str(err.value)


class TestParseInterval:
    """Tests for parse_interval function."""

    def test_parse_interval_hours(self):
        """Test parsing hours format."""
        assert parse_interval("2h") == 120
        assert parse_interval("1h") == 60
        assert parse_interval("24h") == 1440

    def test_parse_interval_minutes(self):
        """Test parsing minutes format."""
        assert parse_interval("30m") == 30
        assert parse_interval("1m") == 1
        assert parse_interval("90m") == 90

    def test_parse_interval_combined(self):
        """Test parsing combined hours and minutes format."""
        assert parse_interval("1h30m") == 90
        assert parse_interval("2h15m") == 135
        assert parse_interval("0h45m") == 45

    def test_parse_interval_case_insensitive(self):
        """Test that parsing is case insensitive."""
        assert parse_interval("2H") == 120
        assert parse_interval("30M") == 30
        assert parse_interval("1H30M") == 90

    def test_parse_interval_with_whitespace(self):
        """Test parsing with leading/trailing whitespace."""
        assert parse_interval("  2h  ") == 120
        assert parse_interval(" 30m ") == 30

    def test_parse_interval_invalid_format(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_interval("invalid")
        assert "Invalid interval format" in str(err.value)

    def test_parse_interval_empty(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_interval("")
        assert "Invalid interval format" in str(err.value)

    def test_parse_interval_zero(self):
        """Test that zero interval raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_interval("0h0m")
        assert "at least 1 minute" in str(err.value)

    def test_parse_interval_too_long(self):
        """Test that interval > 24h raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_interval("25h")
        assert "cannot exceed 24 hours" in str(err.value)


class TestParseDays:
    """Tests for parse_days function."""

    def test_parse_days_single(self):
        """Test parsing single day."""
        assert parse_days("mon") == "mon"
        assert parse_days("fri") == "fri"
        assert parse_days("sun") == "sun"

    def test_parse_days_multiple(self):
        """Test parsing multiple days."""
        assert parse_days("mon,wed,fri") == "mon,wed,fri"
        assert parse_days("sat,sun") == "sat,sun"

    def test_parse_days_all_days(self):
        """Test parsing all days of the week."""
        result = parse_days("mon,tue,wed,thu,fri,sat,sun")
        assert result == "mon,tue,wed,thu,fri,sat,sun"

    def test_parse_days_case_insensitive(self):
        """Test that parsing is case insensitive."""
        assert parse_days("MON") == "mon"
        assert parse_days("Mon,WED,Fri") == "mon,wed,fri"

    def test_parse_days_with_whitespace(self):
        """Test parsing with whitespace."""
        assert parse_days("  mon  ") == "mon"
        assert parse_days("mon, wed, fri") == "mon,wed,fri"

    def test_parse_days_invalid_day(self):
        """Test that invalid day raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_days("monday")
        assert "Invalid day" in str(err.value)

    def test_parse_days_mixed_valid_invalid(self):
        """Test that mix of valid and invalid days raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_days("mon,invalid,fri")
        assert "Invalid day" in str(err.value)

    def test_parse_days_empty(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError) as err:
            parse_days("")
        assert "Invalid day" in str(err.value)
