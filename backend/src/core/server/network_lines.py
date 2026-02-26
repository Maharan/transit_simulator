from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Any, Iterable

from sqlalchemy import and_, func, or_

from core.gtfs.models import Route, Shape, Trip


LINE_FAMILY_ORDER = {
    "u_bahn": 0,
    "s_bahn": 1,
    "a_line": 2,
    "regional": 3,
}

LINE_COLOR_PALETTES = {
    "u_bahn": [
        "#005AAE",
        "#0A72C7",
        "#0080C8",
        "#276FBF",
        "#2B6CB0",
    ],
    "s_bahn": [
        "#007A3D",
        "#0C8A49",
        "#1F9D5A",
        "#2FA84F",
        "#4BAE4F",
    ],
    "regional": [
        "#C33C54",
        "#D1495B",
        "#E76F51",
        "#CF5C36",
        "#A93F55",
    ],
    "a_line": [
        "#B7E000",
        "#D8C6A5",
        "#800020",
        "#8B4513",
    ],
}

LINE_FIXED_COLORS = {
    "U1": "#005AAE",
    "U2": "#D62828",
    "U3": "#F2C300",
    "U4": "#0F8B8D",
    "S1": "#2E9E45",
    "S2": "#7E57C2",
    "S3": "#F28E2B",
    "S5": "#E754A6",
    "A1": "#B7E000",
    "A2": "#D8C6A5",
    "A3": "#800020",
    "A11": "#8B4513",
}

LINE_FIXED_OFFSETS = {
    "U1": -3.0,
    "U2": -1.0,
    "U3": 1.0,
    "U4": 3.0,
    "S1": -3.0,
    "S2": -1.0,
    "S3": 1.0,
    "S5": 3.0,
    "A1": -3.0,
    "A2": -1.0,
    "A3": 1.0,
    "A11": 3.0,
}

LINE_OFFSET_PALETTE = [-4.0, -2.0, 0.0, 2.0, 4.0]
MAX_SHAPE_POINT_GAP_M = 900.0


@dataclass(frozen=True)
class LineShapeRef:
    line_id: str
    line_family: str
    shape_id: str
    route_color: str | None
    trip_count: int


@dataclass(frozen=True)
class ShapePoint:
    shape_id: str
    sequence: int
    lon: float
    lat: float


def classify_transit_line(route_short_name: str | None) -> str | None:
    if not route_short_name:
        return None
    normalized = route_short_name.strip().upper()
    if not normalized:
        return None
    if "SEV" in normalized:
        return None
    if normalized.startswith("U"):
        return "u_bahn"
    if normalized.startswith("S"):
        return "s_bahn"
    if normalized.startswith("RE") or normalized.startswith("RB"):
        return "regional"
    if normalized in {"A1", "A2", "A3", "A11"}:
        return "a_line"
    return None


def normalize_route_color(route_color: str | None) -> str | None:
    if not route_color:
        return None
    normalized = route_color.strip().lstrip("#")
    if len(normalized) != 6:
        return None
    if not all(char in "0123456789ABCDEFabcdef" for char in normalized):
        return None
    return f"#{normalized.upper()}"


def _stable_hash(value: str) -> int:
    seed = 0
    for char in value:
        seed = ((seed << 5) - seed + ord(char)) & 0xFFFFFFFF
    return abs(seed)


def _line_color(*, line_id: str, line_family: str, route_color: str | None) -> str:
    fixed_color = LINE_FIXED_COLORS.get(line_id)
    if fixed_color is not None:
        return fixed_color
    if line_family == "regional":
        return "#000000"
    normalized_color = normalize_route_color(route_color)
    if normalized_color is not None:
        return normalized_color
    palette = LINE_COLOR_PALETTES.get(line_family, LINE_COLOR_PALETTES["regional"])
    return palette[_stable_hash(line_id) % len(palette)]


def _normalize_line_id(route_short_name: str) -> str:
    return route_short_name.strip().upper()


def _line_offset(*, line_id: str, line_family: str) -> float:
    fixed_offset = LINE_FIXED_OFFSETS.get(line_id)
    if fixed_offset is not None:
        return fixed_offset
    if line_family == "regional":
        return 0.0
    return LINE_OFFSET_PALETTE[_stable_hash(line_id) % len(LINE_OFFSET_PALETTE)]


def _distance_m(a: list[float], b: list[float]) -> float:
    lon_a, lat_a = a
    lon_b, lat_b = b
    mean_lat = math.radians((lat_a + lat_b) / 2.0)
    delta_lon = (lon_b - lon_a) * math.cos(mean_lat)
    delta_lat = lat_b - lat_a
    return 111_320.0 * math.sqrt((delta_lon * delta_lon) + (delta_lat * delta_lat))


def _split_shape_by_gap(
    coords: list[list[float]],
    *,
    line_family: str,
) -> list[list[list[float]]]:
    if len(coords) < 2:
        return []
    if len(coords) == 2:
        return [coords]
    if line_family != "s_bahn":
        return [coords]

    segments: list[list[list[float]]] = []
    current_segment: list[list[float]] = [coords[0]]
    last_index = len(coords) - 1

    for index, point in enumerate(coords[1:], start=1):
        is_interior_edge = index > 1 and index < last_index
        if (
            is_interior_edge
            and _distance_m(current_segment[-1], point) > MAX_SHAPE_POINT_GAP_M
        ):
            if len(current_segment) >= 2:
                segments.append(current_segment)
            current_segment = [point]
            continue
        current_segment.append(point)

    if len(current_segment) >= 2:
        segments.append(current_segment)

    return segments


def query_line_shape_refs(*, session, feed_id: str) -> list[LineShapeRef]:
    upper_short_name = func.upper(Route.route_short_name)
    rows = (
        session.query(
            Route.route_short_name,
            Route.route_color,
            Trip.shape_id,
            func.count(Trip.trip_id),
        )
        .join(
            Trip,
            and_(
                Trip.feed_id == Route.feed_id,
                Trip.route_id == Route.route_id,
            ),
        )
        .filter(Route.feed_id == feed_id)
        .filter(Route.route_short_name.isnot(None))
        .filter(Trip.shape_id.isnot(None))
        .filter(
            or_(
                upper_short_name.like("U%"),
                upper_short_name.like("S%"),
                upper_short_name.like("RE%"),
                upper_short_name.like("RB%"),
                upper_short_name.in_(["A1", "A2", "A3", "A11"]),
            )
        )
        .filter(~upper_short_name.contains("SEV"))
        .group_by(Route.route_short_name, Route.route_color, Trip.shape_id)
        .all()
    )

    refs: list[LineShapeRef] = []
    for route_short_name, route_color, shape_id, trip_count in rows:
        if not route_short_name or not shape_id:
            continue
        line_family = classify_transit_line(route_short_name)
        if line_family is None:
            continue
        refs.append(
            LineShapeRef(
                line_id=_normalize_line_id(route_short_name),
                line_family=line_family,
                shape_id=shape_id,
                route_color=route_color,
                trip_count=max(1, int(trip_count or 0)),
            )
        )
    return refs


def query_shape_points(
    *,
    session,
    feed_id: str,
    shape_ids: Iterable[str],
) -> list[ShapePoint]:
    shape_id_list = sorted({shape_id for shape_id in shape_ids if shape_id})
    if not shape_id_list:
        return []

    rows = (
        session.query(
            Shape.shape_id,
            Shape.shape_pt_sequence,
            Shape.shape_pt_lon,
            Shape.shape_pt_lat,
        )
        .filter(Shape.feed_id == feed_id)
        .filter(Shape.shape_id.in_(shape_id_list))
        .filter(Shape.shape_pt_sequence.isnot(None))
        .filter(Shape.shape_pt_lon.isnot(None))
        .filter(Shape.shape_pt_lat.isnot(None))
        .order_by(Shape.shape_id.asc(), Shape.shape_pt_sequence.asc())
        .all()
    )
    points: list[ShapePoint] = []
    for shape_id, sequence, lon, lat in rows:
        if shape_id is None:
            continue
        points.append(
            ShapePoint(
                shape_id=shape_id,
                sequence=int(sequence),
                lon=float(lon),
                lat=float(lat),
            )
        )
    return points


def build_line_feature_collection(
    *,
    line_shape_refs: Iterable[LineShapeRef],
    shape_points: Iterable[ShapePoint],
) -> dict[str, Any]:
    shape_coords_by_id: dict[str, list[list[float]]] = defaultdict(list)
    for point in shape_points:
        shape_coords_by_id[point.shape_id].append([point.lon, point.lat])

    line_shape_ids: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    line_color_hint: dict[tuple[str, str], str | None] = {}
    for ref in line_shape_refs:
        line_key = (ref.line_id, ref.line_family)
        previous_count = line_shape_ids[line_key].get(ref.shape_id, 0)
        line_shape_ids[line_key][ref.shape_id] = max(previous_count, ref.trip_count)
        if line_key not in line_color_hint or line_color_hint[line_key] is None:
            line_color_hint[line_key] = ref.route_color

    features: list[dict[str, Any]] = []
    for line_key in sorted(
        line_shape_ids,
        key=lambda item: (LINE_FAMILY_ORDER.get(item[1], 99), item[0]),
    ):
        line_id, line_family = line_key
        geometry_lines: list[list[list[float]]] = []
        shape_trip_counts = line_shape_ids[line_key]
        if line_family == "s_bahn":
            max_shape_trip_count = max(shape_trip_counts.values(), default=1)
            min_shape_trip_count = max(5, int(round(max_shape_trip_count * 0.1)))
            kept_shape_ids = [
                shape_id
                for shape_id, trip_count in shape_trip_counts.items()
                if trip_count >= min_shape_trip_count
            ]
            if not kept_shape_ids:
                kept_shape_ids = list(shape_trip_counts.keys())
        else:
            # U-Bahn/regional/A-lines can have valid short-turn variants with
            # lower frequency; keep all variants to avoid visual line breaks.
            kept_shape_ids = list(shape_trip_counts.keys())

        for shape_id in sorted(kept_shape_ids):
            coords = shape_coords_by_id.get(shape_id, [])
            geometry_lines.extend(_split_shape_by_gap(coords, line_family=line_family))
        if not geometry_lines:
            continue

        color = _line_color(
            line_id=line_id,
            line_family=line_family,
            route_color=line_color_hint.get(line_key),
        )
        if len(geometry_lines) == 1:
            geometry_type = "LineString"
            coordinates: Any = geometry_lines[0]
        else:
            geometry_type = "MultiLineString"
            coordinates = geometry_lines

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "line_id": line_id,
                    "line_family": line_family,
                    "color": color,
                    "offset_px": _line_offset(line_id=line_id, line_family=line_family),
                },
                "geometry": {
                    "type": geometry_type,
                    "coordinates": coordinates,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def load_network_lines_geojson(*, session, feed_id: str) -> dict[str, Any]:
    line_shape_refs = query_line_shape_refs(session=session, feed_id=feed_id)
    shape_points = query_shape_points(
        session=session,
        feed_id=feed_id,
        shape_ids=[ref.shape_id for ref in line_shape_refs],
    )
    return build_line_feature_collection(
        line_shape_refs=line_shape_refs,
        shape_points=shape_points,
    )
