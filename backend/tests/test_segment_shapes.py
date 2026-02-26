from __future__ import annotations

from core.server import segment_shapes
from core.server.segment_shapes import ShapeProfilePoint, TripStopProfilePoint


def test_base_stop_id_strips_pattern_suffix_and_transfer_prefix() -> None:
    assert (
        segment_shapes._base_stop_id("de:02000:10902:3:109007::pattern_0d302cd8a1ec")
        == "de:02000:10902:3:109007"
    )
    assert (
        segment_shapes._base_stop_id("__same_stop_transfer__de:02000:10902:3:109007")
        == "de:02000:10902:3:109007"
    )


def test_trip_segment_geometry_uses_shape_points_between_stops() -> None:
    segment = {
        "from_stop": {
            "stop_id": "STOP_A::pattern_abc",
            "stop_name": "A",
            "stop_lat": 53.55,
            "stop_lon": 9.99,
        },
        "to_stop": {
            "stop_id": "STOP_B::pattern_abc",
            "stop_name": "B",
            "stop_lat": 53.57,
            "stop_lon": 10.02,
        },
        "edge": {
            "kind": "trip",
            "trip_id": "trip-1",
        },
    }
    geometry = segment_shapes._trip_segment_geometry(
        segment=segment,
        trip_to_shape_id={"trip-1": "shape-1"},
        trip_stop_points_by_trip_id={
            "trip-1": [
                TripStopProfilePoint(stop_id="STOP_A", shape_dist_traveled=0.0),
                TripStopProfilePoint(stop_id="STOP_B", shape_dist_traveled=1200.0),
            ]
        },
        shape_points_by_shape_id={
            "shape-1": [
                ShapeProfilePoint(lon=9.99, lat=53.55, dist_traveled=0.0),
                ShapeProfilePoint(lon=10.01, lat=53.56, dist_traveled=600.0),
                ShapeProfilePoint(lon=10.02, lat=53.57, dist_traveled=1200.0),
            ]
        },
        stop_coords={
            "STOP_A": (9.99, 53.55),
            "STOP_B": (10.02, 53.57),
        },
    )

    assert geometry == [[9.99, 53.55], [10.01, 53.56], [10.02, 53.57]]


def test_segment_fallback_geometry_uses_stop_coordinates() -> None:
    segment = {
        "from_stop": {"stop_lat": 53.55, "stop_lon": 9.99},
        "to_stop": {"stop_lat": 53.57, "stop_lon": 10.02},
    }
    geometry = segment_shapes._segment_fallback_geometry(segment)

    assert geometry == [[9.99, 53.55], [10.02, 53.57]]
