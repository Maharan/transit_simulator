from __future__ import annotations

from core.server.population_grid import (
    PopulationGridCellRecord,
    build_population_grid_feature_collection,
    estimate_population,
)


def test_estimate_population_uses_numeric_value_when_available() -> None:
    assert (
        estimate_population(
            experimental_population=42,
            experimental_population_raw="[0-3]",
        )
        == 42.0
    )


def test_estimate_population_uses_masked_bucket_midpoint() -> None:
    assert (
        estimate_population(
            experimental_population=None,
            experimental_population_raw="[0-3]",
        )
        == 1.5
    )


def test_build_population_grid_feature_collection_emits_polygon_geojson() -> None:
    payload = build_population_grid_feature_collection(
        [
            PopulationGridCellRecord(
                grid_cell_id="CRS3035RES1kmN2725000E4321000",
                northing_m=2_725_000,
                easting_m=4_321_000,
                grid_resolution_m=1000,
                population_estimate=125.0,
                population_raw="125",
                plausibility_label="plausibel",
            )
        ]
    )

    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["properties"] == {
        "population_estimate": 125.0,
    }
    assert payload["features"][0]["geometry"]["type"] == "Polygon"
    assert len(payload["features"][0]["geometry"]["coordinates"][0]) == 5
