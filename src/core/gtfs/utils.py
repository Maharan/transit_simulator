from __future__ import annotations

import math

from sqlalchemy import func

from core.gtfs.models import Stop


def resolve_feed_id(session, requested_feed_id: str | None) -> str:
    if requested_feed_id:
        return requested_feed_id
    rows = session.query(Stop.feed_id).distinct().all()
    feed_ids = [row[0] for row in rows if row[0]]
    if len(feed_ids) == 1:
        return feed_ids[0]
    if not feed_ids:
        raise SystemExit("No feeds found in gtfs.stops.")
    raise SystemExit(
        "Multiple feeds found. Provide --feed-id. "
        f"Available: {', '.join(sorted(feed_ids))}"
    )


def resolve_stop_by_name(session, feed_id: str, name: str) -> tuple[str, str]:
    normalized = name.strip().lower()
    if not normalized:
        raise SystemExit("Stop name cannot be empty.")

    exact = (
        session.query(Stop.stop_id, Stop.stop_name)
        .filter(Stop.feed_id == feed_id)
        .filter(Stop.stop_name.isnot(None))
        .filter(func.lower(Stop.stop_name) == normalized)
        .all()
    )
    if len(exact) == 1:
        return exact[0][0], exact[0][1]
    if len(exact) > 1:
        options = ", ".join(f"{row[1]} ({row[0]})" for row in exact[:10])
        raise SystemExit(
            f"Multiple stops match '{name}'. Be more specific. Examples: {options}"
        )

    like = (
        session.query(Stop.stop_id, Stop.stop_name)
        .filter(Stop.feed_id == feed_id)
        .filter(Stop.stop_name.isnot(None))
        .filter(func.lower(Stop.stop_name).like(f"%{normalized}%"))
        .all()
    )
    if len(like) == 1:
        return like[0][0], like[0][1]
    if not like:
        raise SystemExit(f"No stops found matching '{name}'.")
    options = ", ".join(f"{row[1]} ({row[0]})" for row in like[:10])
    raise SystemExit(
        f"Multiple stops match '{name}'. Be more specific. Examples: {options}"
    )


def resolve_stops_by_coordinates(
    session,
    feed_id: str,
    lat: float,
    lon: float,
    *,
    max_candidates: int = 1,
    max_distance_m: float | None = None,
) -> list[tuple[str, str, float]]:
    if lat < -90 or lat > 90:
        raise SystemExit("--from-lat/--to-lat must be between -90 and 90.")
    if lon < -180 or lon > 180:
        raise SystemExit("--from-lon/--to-lon must be between -180 and 180.")
    if max_candidates <= 0:
        raise SystemExit("--coord-max-candidates must be > 0.")
    if max_distance_m is not None and max_distance_m <= 0:
        raise SystemExit("--coord-max-distance-m must be > 0.")

    rows = (
        session.query(Stop.stop_id, Stop.stop_name, Stop.stop_lat, Stop.stop_lon)
        .filter(Stop.feed_id == feed_id)
        .filter(Stop.stop_id.isnot(None))
        .filter(Stop.stop_lat.isnot(None))
        .filter(Stop.stop_lon.isnot(None))
        .yield_per(5000)
    )

    matches: list[tuple[str, str, float]] = []
    for stop_id, stop_name, stop_lat, stop_lon in rows:
        if not stop_id or stop_lat is None or stop_lon is None:
            continue
        distance_m = _haversine_distance_m(lat, lon, float(stop_lat), float(stop_lon))
        if max_distance_m is not None and distance_m > max_distance_m:
            continue
        matches.append((stop_id, stop_name or stop_id, distance_m))

    if not matches:
        if max_distance_m is not None:
            raise SystemExit(
                "No stops found near coordinates "
                f"({lat:.6f}, {lon:.6f}) within {max_distance_m:.0f}m."
            )
        raise SystemExit(f"No stops with coordinates found for feed '{feed_id}'.")

    matches.sort(key=lambda row: row[2])
    return matches[:max_candidates]


def resolve_stop_by_coordinates(
    session,
    feed_id: str,
    lat: float,
    lon: float,
) -> tuple[str, str, float]:
    matches = resolve_stops_by_coordinates(
        session=session,
        feed_id=feed_id,
        lat=lat,
        lon=lon,
        max_candidates=1,
    )
    return matches[0]


def _haversine_distance_m(
    lat_a: float,
    lon_a: float,
    lat_b: float,
    lon_b: float,
) -> float:
    earth_radius_m = 6_371_000.0
    lat_a_rad = math.radians(lat_a)
    lon_a_rad = math.radians(lon_a)
    lat_b_rad = math.radians(lat_b)
    lon_b_rad = math.radians(lon_b)
    delta_lat = lat_b_rad - lat_a_rad
    delta_lon = lon_b_rad - lon_a_rad
    sin_lat = math.sin(delta_lat / 2.0)
    sin_lon = math.sin(delta_lon / 2.0)
    a = (
        sin_lat * sin_lat
        + math.cos(lat_a_rad) * math.cos(lat_b_rad) * sin_lon * sin_lon
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_m * c
