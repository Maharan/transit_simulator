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
    assert (
        segment_shapes._base_stop_id("de:02000:60010::600052")
        == "de:02000:60010::600052"
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


def test_trip_segment_geometry_prefers_exact_real_stop_ids_with_double_colons() -> None:
    segment = {
        "from_stop": {
            "stop_id": "de:02000:62025::620091",
            "stop_name": "A",
            "stop_lat": 53.55,
            "stop_lon": 9.99,
        },
        "to_stop": {
            "stop_id": "de:02000:60010::600052",
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
                TripStopProfilePoint(
                    stop_id="de:02000:62025::620091",
                    shape_dist_traveled=0.0,
                ),
                TripStopProfilePoint(
                    stop_id="de:02000:60010::600052",
                    shape_dist_traveled=1200.0,
                ),
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
            "de:02000:62025::620091": (9.99, 53.55),
            "de:02000:60010::600052": (10.02, 53.57),
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


def test_segment_fallback_geometry_creates_loop_for_same_point_transfer() -> None:
    segment = {
        "from_stop": {"stop_lat": 53.55, "stop_lon": 9.99},
        "to_stop": {"stop_lat": 53.55, "stop_lon": 9.99},
        "edge": {"kind": "transfer"},
    }
    geometry = segment_shapes._segment_fallback_geometry(segment)

    assert geometry is not None
    assert len(geometry) > 2
    assert geometry[0] == [9.99, 53.55]
    assert geometry[-1] == [9.99, 53.55]
    assert any(point != [9.99, 53.55] for point in geometry[1:-1])


def test_normalize_route_color_accepts_six_digit_hex() -> None:
    assert segment_shapes._normalize_route_color("005aae") == "#005AAE"
    assert segment_shapes._normalize_route_color("#ffffff") == "#FFFFFF"
    assert segment_shapes._normalize_route_color("xyz") is None
