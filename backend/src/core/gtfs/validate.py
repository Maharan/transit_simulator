from __future__ import annotations

from pathlib import Path


GTFS_REQUIRED_FILES = {
    "agency.txt",
    "calendar.txt",
    "calendar_dates.txt",
    "routes.txt",
    "stops.txt",
    "stop_times.txt",
    "trips.txt",
}


GTFS_OPTIONAL_FILES = {
    "feed_info.txt",
    "frequencies.txt",
    "shapes.txt",
    "transfers.txt",
}


def find_gtfs_files(folder: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in folder.glob("*.txt"):
        files[path.name] = path
    return files


def missing_required_files(folder: Path) -> set[str]:
    files = find_gtfs_files(folder)
    return {name for name in GTFS_REQUIRED_FILES if name not in files}
