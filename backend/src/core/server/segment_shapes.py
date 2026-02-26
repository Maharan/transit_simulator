from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.gtfs.models import Shape, Stop, StopTime, Trip


@dataclass(frozen=True)
class ShapeProfilePoint:
    lon: float
    lat: float
    dist_traveled: float | None


@dataclass(frozen=True)
class TripStopProfilePoint:
    stop_id: str
    shape_dist_traveled: float | None


def _base_stop_id(stop_id: str | None) -> str | None:
    if not stop_id:
        return None
    if stop_id.startswith("__same_stop_transfer__"):
        stop_id = stop_id.replace("__same_stop_transfer__", "", 1)
    if "::" in stop_id:
        return stop_id.split("::", 1)[0]
    return stop_id


def _squared_distance(
    point_a: tuple[float, float], point_b: tuple[float, float]
) -> float:
    lon_a, lat_a = point_a
    lon_b, lat_b = point_b
    d_lon = lon_a - lon_b
    d_lat = lat_a - lat_b
    return d_lon * d_lon + d_lat * d_lat


def _nearest_index_for_coord(
    points: list[ShapeProfilePoint], target_coord: tuple[float, float]
) -> int | None:
    if not points:
        return None
    best_index = 0
    best_distance = float("inf")
    for index, point in enumerate(points):
        dist = _squared_distance((point.lon, point.lat), target_coord)
        if dist < best_distance:
            best_distance = dist
            best_index = index
    return best_index


def _nearest_index_for_distance(
    points: list[ShapeProfilePoint], target_distance: float
) -> int | None:
    best_index = None
    best_distance = float("inf")
    for index, point in enumerate(points):
        if point.dist_traveled is None:
            continue
        dist = abs(point.dist_traveled - target_distance)
        if dist < best_distance:
            best_distance = dist
            best_index = index
    return best_index


def _extract_shape_slice(
    *,
    shape_points: list[ShapeProfilePoint],
    from_shape_dist: float | None,
    to_shape_dist: float | None,
    from_coord: tuple[float, float] | None,
    to_coord: tuple[float, float] | None,
) -> list[list[float]]:
    if len(shape_points) < 2:
        return []

    start_index = None
    end_index = None
    if from_shape_dist is not None and to_shape_dist is not None:
        start_index = _nearest_index_for_distance(shape_points, from_shape_dist)
        end_index = _nearest_index_for_distance(shape_points, to_shape_dist)

    if start_index is None and from_coord is not None:
        start_index = _nearest_index_for_coord(shape_points, from_coord)
    if end_index is None and to_coord is not None:
        end_index = _nearest_index_for_coord(shape_points, to_coord)

    if start_index is None or end_index is None:
        return []
    if start_index == end_index:
        if end_index + 1 < len(shape_points):
            end_index += 1
        elif start_index > 0:
            start_index -= 1
        else:
            return []

    if start_index <= end_index:
        window = shape_points[start_index : end_index + 1]
    else:
        window = list(reversed(shape_points[end_index : start_index + 1]))
    return [[point.lon, point.lat] for point in window]


def _segment_fallback_geometry(segment: dict[str, Any]) -> list[list[float]] | None:
    from_stop = segment.get("from_stop")
    to_stop = segment.get("to_stop")
    if not isinstance(from_stop, dict) or not isinstance(to_stop, dict):
        return None
    from_lon = from_stop.get("stop_lon")
    from_lat = from_stop.get("stop_lat")
    to_lon = to_stop.get("stop_lon")
    to_lat = to_stop.get("stop_lat")
    if not all(
        isinstance(value, (int, float))
        for value in [from_lon, from_lat, to_lon, to_lat]
    ):
        return None
    return [[float(from_lon), float(from_lat)], [float(to_lon), float(to_lat)]]


def _find_trip_stop_pair(
    *,
    trip_stop_points: list[TripStopProfilePoint],
    from_stop_id: str,
    to_stop_id: str,
) -> tuple[TripStopProfilePoint, TripStopProfilePoint] | None:
    for from_index, from_point in enumerate(trip_stop_points):
        if from_point.stop_id != from_stop_id:
            continue
        for to_index in range(from_index + 1, len(trip_stop_points)):
            to_point = trip_stop_points[to_index]
            if to_point.stop_id == to_stop_id:
                return from_point, to_point
    return None


def _trip_segment_geometry(
    *,
    segment: dict[str, Any],
    trip_to_shape_id: dict[str, str],
    trip_stop_points_by_trip_id: dict[str, list[TripStopProfilePoint]],
    shape_points_by_shape_id: dict[str, list[ShapeProfilePoint]],
    stop_coords: dict[str, tuple[float, float]],
) -> list[list[float]] | None:
    edge = segment.get("edge")
    if not isinstance(edge, dict):
        return None
    if edge.get("kind") != "trip":
        return None
    trip_id = edge.get("trip_id")
    if not isinstance(trip_id, str) or not trip_id:
        return None

    from_stop = segment.get("from_stop")
    to_stop = segment.get("to_stop")
    if not isinstance(from_stop, dict) or not isinstance(to_stop, dict):
        return None

    from_stop_id = _base_stop_id(from_stop.get("stop_id"))
    to_stop_id = _base_stop_id(to_stop.get("stop_id"))
    if not from_stop_id or not to_stop_id:
        return None

    trip_stops = trip_stop_points_by_trip_id.get(trip_id)
    if not trip_stops:
        return None
    stop_pair = _find_trip_stop_pair(
        trip_stop_points=trip_stops,
        from_stop_id=from_stop_id,
        to_stop_id=to_stop_id,
    )
    if stop_pair is None:
        return None

    shape_id = trip_to_shape_id.get(trip_id)
    if not shape_id:
        return None
    shape_points = shape_points_by_shape_id.get(shape_id, [])
    if len(shape_points) < 2:
        return None

    from_stop_point, to_stop_point = stop_pair
    segment_shape = _extract_shape_slice(
        shape_points=shape_points,
        from_shape_dist=from_stop_point.shape_dist_traveled,
        to_shape_dist=to_stop_point.shape_dist_traveled,
        from_coord=stop_coords.get(from_stop_id),
        to_coord=stop_coords.get(to_stop_id),
    )
    if len(segment_shape) >= 2:
        return segment_shape
    return None


def attach_path_segment_geometries(
    *,
    session,
    feed_id: str,
    path_segments: list[dict[str, Any]],
) -> None:
    if not path_segments:
        return

    trip_ids = {
        edge.get("trip_id")
        for segment in path_segments
        for edge in [segment.get("edge")]
        if isinstance(edge, dict)
        and edge.get("kind") == "trip"
        and isinstance(edge.get("trip_id"), str)
        and edge.get("trip_id")
    }
    trip_id_values = sorted(trip_ids)
    if not trip_id_values:
        for segment in path_segments:
            segment["geometry"] = _segment_fallback_geometry(segment)
        return

    trip_rows = (
        session.query(Trip.trip_id, Trip.shape_id)
        .filter(Trip.feed_id == feed_id)
        .filter(Trip.trip_id.in_(trip_id_values))
        .all()
    )
    trip_to_shape_id = {
        trip_id: shape_id
        for trip_id, shape_id in trip_rows
        if isinstance(trip_id, str) and isinstance(shape_id, str) and shape_id
    }

    stop_time_rows = (
        session.query(
            StopTime.trip_id,
            StopTime.stop_id,
            StopTime.stop_sequence,
            StopTime.shape_dist_traveled,
        )
        .filter(StopTime.feed_id == feed_id)
        .filter(StopTime.trip_id.in_(trip_id_values))
        .filter(StopTime.stop_id.isnot(None))
        .filter(StopTime.stop_sequence.isnot(None))
        .order_by(StopTime.trip_id.asc(), StopTime.stop_sequence.asc())
        .all()
    )
    trip_stop_points_by_trip_id: dict[str, list[TripStopProfilePoint]] = {}
    stop_ids: set[str] = set()
    for trip_id, stop_id, _stop_sequence, shape_dist in stop_time_rows:
        if not isinstance(trip_id, str) or not isinstance(stop_id, str):
            continue
        stop_ids.add(stop_id)
        trip_stop_points_by_trip_id.setdefault(trip_id, []).append(
            TripStopProfilePoint(
                stop_id=stop_id,
                shape_dist_traveled=float(shape_dist)
                if isinstance(shape_dist, (int, float))
                else None,
            )
        )

    stop_rows = (
        session.query(Stop.stop_id, Stop.stop_lon, Stop.stop_lat)
        .filter(Stop.feed_id == feed_id)
        .filter(Stop.stop_id.in_(sorted(stop_ids)))
        .filter(Stop.stop_lon.isnot(None))
        .filter(Stop.stop_lat.isnot(None))
        .all()
    )
    stop_coords = {
        stop_id: (float(stop_lon), float(stop_lat))
        for stop_id, stop_lon, stop_lat in stop_rows
        if isinstance(stop_id, str)
    }

    shape_ids = sorted(set(trip_to_shape_id.values()))
    shape_point_rows = (
        session.query(
            Shape.shape_id,
            Shape.shape_pt_sequence,
            Shape.shape_pt_lon,
            Shape.shape_pt_lat,
            Shape.shape_dist_traveled,
        )
        .filter(Shape.feed_id == feed_id)
        .filter(Shape.shape_id.in_(shape_ids))
        .filter(Shape.shape_pt_sequence.isnot(None))
        .filter(Shape.shape_pt_lon.isnot(None))
        .filter(Shape.shape_pt_lat.isnot(None))
        .order_by(Shape.shape_id.asc(), Shape.shape_pt_sequence.asc())
        .all()
    )
    shape_points_by_shape_id: dict[str, list[ShapeProfilePoint]] = {}
    for shape_id, _sequence, lon, lat, dist_traveled in shape_point_rows:
        if not isinstance(shape_id, str):
            continue
        shape_points_by_shape_id.setdefault(shape_id, []).append(
            ShapeProfilePoint(
                lon=float(lon),
                lat=float(lat),
                dist_traveled=float(dist_traveled)
                if isinstance(dist_traveled, (int, float))
                else None,
            )
        )

    for segment in path_segments:
        geometry = _trip_segment_geometry(
            segment=segment,
            trip_to_shape_id=trip_to_shape_id,
            trip_stop_points_by_trip_id=trip_stop_points_by_trip_id,
            shape_points_by_shape_id=shape_points_by_shape_id,
            stop_coords=stop_coords,
        )
        if geometry is None:
            geometry = _segment_fallback_geometry(segment)
        segment["geometry"] = geometry
