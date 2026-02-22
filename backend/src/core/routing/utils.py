from __future__ import annotations


def parse_time_to_seconds(time_str: str | None) -> int | None:
    if not time_str:
        return None
    parts = time_str.split(":")
    if len(parts) != 3:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except ValueError:
        return None
    if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
        return None
    return hours * 3600 + minutes * 60 + seconds


def seconds_to_time_str(total_seconds: int | None) -> str | None:
    if total_seconds is None:
        return None
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
