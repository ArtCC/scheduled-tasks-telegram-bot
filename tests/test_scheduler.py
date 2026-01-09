from datetime import datetime

import pytest

from scheduled_bot.scheduler import parse_time_spec


def test_parse_time_spec_daily():
    hour, minute, run_at, tz = parse_time_spec("08:30", "UTC")
    assert (hour, minute) == (8, 30)
    assert run_at is None
    assert tz == "UTC"


def test_parse_time_spec_once():
    hour, minute, run_at, tz = parse_time_spec("2025-12-31T23:59", "UTC")
    assert (hour, minute) == (23, 59)
    assert isinstance(run_at, datetime)
    assert tz == "UTC"


def test_parse_time_spec_with_timezone_override():
    hour, minute, run_at, tz = parse_time_spec("07:15", "Europe/Madrid")
    assert (hour, minute) == (7, 15)
    assert run_at is None
    assert tz == "Europe/Madrid"


def test_parse_time_spec_invalid_timezone():
    with pytest.raises(ValueError) as err:
        parse_time_spec("08:00", "Invalid/Zone")
    assert "Zona horaria inválida" in str(err.value)


def test_parse_time_spec_once_with_zulu():
    hour, minute, run_at, tz = parse_time_spec("2025-12-31T23:59Z", "UTC")
    assert (hour, minute) == (23, 59)
    assert isinstance(run_at, datetime)
    assert run_at.tzinfo is not None
    assert tz == "UTC"
