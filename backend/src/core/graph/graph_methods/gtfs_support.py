from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.gtfs.models import Stop, Trip

DEFAULT_WALK_MAX_DISTANCE_M = 500
DEFAULT_WALK_SPEED_MPS = 1.4
DEFAULT_WALK_MAX_NEIGHBORS = 8


@dataclass(frozen=True, slots=True)
class StopBuildContext:
    canonical_stop_by_stop_id: dict[str, str]
    coordinates_by_canonical_stop_id: dict[str, tuple[float, float]]
    stop_count: int


@dataclass(frozen=True, slots=True)
class TripBuildMetadata:
    route_id: str | None
    service_id: str | None
    direction_id: int | None = None


EMPTY_TRIP_BUILD_METADATA = TripBuildMetadata(
    route_id=None,
    service_id=None,
    direction_id=None,
)


def time_to_seconds(time_str: str | None) -> int | None:
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


def edge_timing(
    dep_time: str | None,
    arr_time: str | None,
) -> tuple[int | None, int | None, int | None]:
    dep_sec = time_to_seconds(dep_time)
    arr_sec = time_to_seconds(arr_time)
    if dep_sec is None or arr_sec is None:
        return None, dep_sec, arr_sec
    weight = arr_sec - dep_sec
    if weight < 0:
        return None, dep_sec, arr_sec
    return weight, dep_sec, arr_sec


def load_parent_stop_coords(
    session: Session,
    feed_id: str,
    *,
    known_nodes: set[str] | None = None,
) -> dict[str, tuple[float, float]]:
    rows = (
        session.query(Stop.stop_id, Stop.parent_station, Stop.stop_lat, Stop.stop_lon)
        .filter(Stop.feed_id == feed_id)
        .yield_per(5000)
    )
    parent_stop_coords: dict[str, tuple[float, float]] = {}
    for stop_id, parent_station, stop_lat, stop_lon in rows:
        if not stop_id or stop_lat is None or stop_lon is None:
            continue
        canonical_stop_id = parent_station or stop_id
        if known_nodes is not None and canonical_stop_id not in known_nodes:
            continue
        parent_stop_coords.setdefault(
            canonical_stop_id,
            (float(stop_lat), float(stop_lon)),
        )
    return parent_stop_coords


def load_stop_context(
    session: Session,
    feed_id: str,
    *,
    progress: bool = False,
    progress_every: int = 5000,
    progress_label: str | None = None,
) -> StopBuildContext:
    parent_map: dict[str, str] = {}
    parent_stop_coords: dict[str, tuple[float, float]] = {}
    stop_rows = (
        session.query(Stop.stop_id, Stop.parent_station, Stop.stop_lat, Stop.stop_lon)
        .filter(Stop.feed_id == feed_id)
        .yield_per(5000)
    )

    stop_count = 0
    for stop_id, parent_station, stop_lat, stop_lon in stop_rows:
        if not stop_id:
            continue
        canonical_stop_id = parent_station or stop_id
        parent_map[stop_id] = canonical_stop_id
        if stop_lat is not None and stop_lon is not None:
            parent_stop_coords.setdefault(
                canonical_stop_id,
                (float(stop_lat), float(stop_lon)),
            )
        stop_count += 1
        if progress and stop_count % progress_every == 0:
            suffix = f" {progress_label}" if progress_label else ""
            print(f"Loaded {stop_count} stops{suffix}...")

    if progress:
        suffix = f" {progress_label}" if progress_label else ""
        print(f"Loaded {stop_count} stops{suffix} total.")

    return StopBuildContext(
        canonical_stop_by_stop_id=parent_map,
        coordinates_by_canonical_stop_id=parent_stop_coords,
        stop_count=stop_count,
    )


def load_trip_metadata(
    session: Session,
    feed_id: str,
) -> dict[str, TripBuildMetadata]:
    trip_meta: dict[str, TripBuildMetadata] = {}
    trip_rows = (
        session.query(Trip.trip_id, Trip.route_id, Trip.service_id, Trip.direction_id)
        .filter(Trip.feed_id == feed_id)
        .yield_per(5000)
    )
    for trip_id, route_id, service_id, direction_id in trip_rows:
        if not trip_id:
            continue
        trip_meta[trip_id] = TripBuildMetadata(
            route_id=route_id,
            service_id=service_id,
            direction_id=direction_id,
        )
    return trip_meta
