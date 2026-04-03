from __future__ import annotations

from core.server.floor_space_density import (
    FloorSpaceCellRecord,
    build_floor_space_feature_collection,
)


def test_build_floor_space_feature_collection_emits_point_geojson() -> None:
    payload = build_floor_space_feature_collection(
        [
            FloorSpaceCellRecord(
                center_lat=53.55,
                center_lon=9.99,
                building_count=4,
                floor_space_m2=2800.0,
                floor_space_density_sqkm=280000.0,
                population_estimate=140.0,
                population_density_sqkm=14000.0,
            )
        ]
    )

    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["properties"] == {
        "building_count": 4,
        "floor_space_m2": 2800.0,
        "floor_space_density_sqkm": 280000.0,
        "population_estimate": 140.0,
        "population_density_sqkm": 14000.0,
    }
    assert payload["features"][0]["geometry"] == {
        "type": "Point",
        "coordinates": [9.99, 53.55],
    }
