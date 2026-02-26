from __future__ import annotations

from core.server.network_lines import (
    LineShapeRef,
    ShapePoint,
    build_line_feature_collection,
    classify_transit_line,
)


def test_classify_transit_line_supports_expected_hamburg_modes() -> None:
    assert classify_transit_line("U1") == "u_bahn"
    assert classify_transit_line("S3") == "s_bahn"
    assert classify_transit_line("A11") == "a_line"
    assert classify_transit_line("RE7") == "regional"
    assert classify_transit_line("RB81") == "regional"
    assert classify_transit_line("SEV U1") is None
    assert classify_transit_line("X35") is None


def test_build_line_feature_collection_aggregates_shapes_per_line() -> None:
    line_shape_refs = [
        LineShapeRef(
            line_id="U1",
            line_family="u_bahn",
            shape_id="shape_u_1",
            route_color=None,
            trip_count=50,
        ),
        LineShapeRef(
            line_id="U1",
            line_family="u_bahn",
            shape_id="shape_u_2",
            route_color=None,
            trip_count=40,
        ),
        LineShapeRef(
            line_id="S1",
            line_family="s_bahn",
            shape_id="shape_s_1",
            route_color="00AA55",
            trip_count=30,
        ),
        LineShapeRef(
            line_id="RE7",
            line_family="regional",
            shape_id="shape_re_1",
            route_color="FF0000",
            trip_count=25,
        ),
        LineShapeRef(
            line_id="A1",
            line_family="a_line",
            shape_id="shape_a_1",
            route_color=None,
            trip_count=12,
        ),
    ]
    shape_points = [
        ShapePoint(shape_id="shape_u_1", sequence=1, lon=9.95, lat=53.55),
        ShapePoint(shape_id="shape_u_1", sequence=2, lon=10.01, lat=53.57),
        ShapePoint(shape_id="shape_u_2", sequence=1, lon=10.01, lat=53.57),
        ShapePoint(shape_id="shape_u_2", sequence=2, lon=10.08, lat=53.60),
        ShapePoint(shape_id="shape_s_1", sequence=1, lon=9.99, lat=53.50),
        ShapePoint(shape_id="shape_s_1", sequence=2, lon=10.11, lat=53.56),
        ShapePoint(shape_id="shape_re_1", sequence=1, lon=10.02, lat=53.48),
        ShapePoint(shape_id="shape_re_1", sequence=2, lon=10.25, lat=53.62),
        ShapePoint(shape_id="shape_a_1", sequence=1, lon=9.84, lat=53.58),
        ShapePoint(shape_id="shape_a_1", sequence=2, lon=10.09, lat=53.57),
    ]

    collection = build_line_feature_collection(
        line_shape_refs=line_shape_refs,
        shape_points=shape_points,
    )

    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 4

    first_feature = collection["features"][0]
    second_feature = collection["features"][1]
    third_feature = collection["features"][2]
    fourth_feature = collection["features"][3]

    assert first_feature["properties"]["line_id"] == "U1"
    assert first_feature["properties"]["line_family"] == "u_bahn"
    assert first_feature["geometry"]["type"] == "MultiLineString"
    assert len(first_feature["geometry"]["coordinates"]) == 2
    assert first_feature["properties"]["offset_px"] == -3.0

    assert second_feature["properties"]["line_id"] == "S1"
    assert second_feature["properties"]["line_family"] == "s_bahn"
    assert second_feature["properties"]["color"] == "#2E9E45"
    assert second_feature["geometry"]["type"] == "LineString"
    assert second_feature["properties"]["offset_px"] == -3.0

    assert third_feature["properties"]["line_id"] == "A1"
    assert third_feature["properties"]["line_family"] == "a_line"
    assert third_feature["properties"]["color"] == "#B7E000"

    assert fourth_feature["properties"]["line_id"] == "RE7"
    assert fourth_feature["properties"]["line_family"] == "regional"
    assert fourth_feature["properties"]["color"] == "#000000"


def test_build_line_feature_collection_skips_low_frequency_outlier_shapes() -> None:
    line_shape_refs = [
        LineShapeRef(
            line_id="S5",
            line_family="s_bahn",
            shape_id="shape_main",
            route_color=None,
            trip_count=300,
        ),
        LineShapeRef(
            line_id="S5",
            line_family="s_bahn",
            shape_id="shape_variant",
            route_color=None,
            trip_count=5,
        ),
    ]
    shape_points = [
        ShapePoint(shape_id="shape_main", sequence=1, lon=9.9, lat=53.5),
        ShapePoint(shape_id="shape_main", sequence=2, lon=10.2, lat=53.6),
        ShapePoint(shape_id="shape_variant", sequence=1, lon=10.0, lat=53.6),
        ShapePoint(shape_id="shape_variant", sequence=2, lon=10.3, lat=53.8),
    ]

    collection = build_line_feature_collection(
        line_shape_refs=line_shape_refs,
        shape_points=shape_points,
    )

    assert len(collection["features"]) == 1
    line_feature = collection["features"][0]
    assert line_feature["properties"]["line_id"] == "S5"
    assert line_feature["geometry"]["type"] == "LineString"
    assert line_feature["geometry"]["coordinates"] == [[9.9, 53.5], [10.2, 53.6]]


def test_build_line_feature_collection_splits_discontinuous_shape_gaps() -> None:
    line_shape_refs = [
        LineShapeRef(
            line_id="S1",
            line_family="s_bahn",
            shape_id="shape_s_1",
            route_color=None,
            trip_count=100,
        )
    ]
    # Point 3 is intentionally far from point 2, so the renderer should split
    # the geometry instead of drawing an artificial straight connector.
    shape_points = [
        ShapePoint(shape_id="shape_s_1", sequence=1, lon=9.90, lat=53.55),
        ShapePoint(shape_id="shape_s_1", sequence=2, lon=9.91, lat=53.56),
        ShapePoint(shape_id="shape_s_1", sequence=3, lon=9.95, lat=53.57),
        ShapePoint(shape_id="shape_s_1", sequence=4, lon=9.96, lat=53.58),
    ]

    collection = build_line_feature_collection(
        line_shape_refs=line_shape_refs,
        shape_points=shape_points,
    )

    assert len(collection["features"]) == 1
    line_feature = collection["features"][0]
    assert line_feature["properties"]["line_id"] == "S1"
    assert line_feature["geometry"]["type"] == "MultiLineString"
    assert line_feature["geometry"]["coordinates"] == [
        [[9.9, 53.55], [9.91, 53.56]],
        [[9.95, 53.57], [9.96, 53.58]],
    ]


def test_build_line_feature_collection_keeps_u_bahn_with_large_gap_connected() -> None:
    line_shape_refs = [
        LineShapeRef(
            line_id="U1",
            line_family="u_bahn",
            shape_id="shape_u_1",
            route_color=None,
            trip_count=100,
        )
    ]
    # U-Bahn shapes can legitimately have sparse points between stations.
    shape_points = [
        ShapePoint(shape_id="shape_u_1", sequence=1, lon=10.10, lat=53.63),
        ShapePoint(shape_id="shape_u_1", sequence=2, lon=10.12, lat=53.62),
        ShapePoint(shape_id="shape_u_1", sequence=3, lon=10.14, lat=53.61),
        ShapePoint(shape_id="shape_u_1", sequence=4, lon=10.16, lat=53.60),
    ]

    collection = build_line_feature_collection(
        line_shape_refs=line_shape_refs,
        shape_points=shape_points,
    )

    assert len(collection["features"]) == 1
    line_feature = collection["features"][0]
    assert line_feature["properties"]["line_id"] == "U1"
    assert line_feature["geometry"]["type"] == "LineString"
    assert line_feature["geometry"]["coordinates"] == [
        [10.1, 53.63],
        [10.12, 53.62],
        [10.14, 53.61],
        [10.16, 53.6],
    ]


def test_build_line_feature_collection_keeps_low_frequency_u_bahn_variants() -> None:
    line_shape_refs = [
        LineShapeRef(
            line_id="U1",
            line_family="u_bahn",
            shape_id="shape_u_main",
            route_color=None,
            trip_count=200,
        ),
        LineShapeRef(
            line_id="U1",
            line_family="u_bahn",
            shape_id="shape_u_short_turn",
            route_color=None,
            trip_count=3,
        ),
    ]
    shape_points = [
        ShapePoint(shape_id="shape_u_main", sequence=1, lon=10.08, lat=53.62),
        ShapePoint(shape_id="shape_u_main", sequence=2, lon=10.12, lat=53.64),
        ShapePoint(shape_id="shape_u_short_turn", sequence=1, lon=10.12, lat=53.64),
        ShapePoint(shape_id="shape_u_short_turn", sequence=2, lon=10.15, lat=53.66),
    ]

    collection = build_line_feature_collection(
        line_shape_refs=line_shape_refs,
        shape_points=shape_points,
    )

    assert len(collection["features"]) == 1
    line_feature = collection["features"][0]
    assert line_feature["properties"]["line_id"] == "U1"
    assert line_feature["geometry"]["type"] == "MultiLineString"
    assert len(line_feature["geometry"]["coordinates"]) == 2
