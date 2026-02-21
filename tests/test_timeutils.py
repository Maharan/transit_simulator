from __future__ import annotations

from core.routing.utils import parse_time_to_seconds, seconds_to_time_str


def test_parse_time_to_seconds_handles_valid_and_invalid_inputs() -> None:
    assert parse_time_to_seconds("00:00:00") == 0
    assert parse_time_to_seconds("24:10:05") == 87005
    assert parse_time_to_seconds("12:60:00") is None
    assert parse_time_to_seconds("not-a-time") is None
    assert parse_time_to_seconds(None) is None


def test_seconds_to_time_str_round_trip_like_formatting() -> None:
    assert seconds_to_time_str(0) == "00:00:00"
    assert seconds_to_time_str(87005) == "24:10:05"
    assert seconds_to_time_str(None) is None
