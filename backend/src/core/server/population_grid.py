from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyproj import Transformer

from core.demographics.models import PopulationGridCell


MASKED_POPULATION_ESTIMATE = 1.5
GRID_TO_WGS84 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
POPULATION_COORD_PRECISION = 6


@dataclass(frozen=True)
class PopulationGridCellRecord:
    grid_cell_id: str
    northing_m: int
    easting_m: int
    grid_resolution_m: int
    population_estimate: float
    population_raw: str | None
    plausibility_label: str | None


@dataclass(frozen=True)
class PopulationGridCellFeature:
    ring_coordinates: list[list[float]]
    population_estimate: float


def estimate_population(
    *,
    experimental_population: int | None,
    experimental_population_raw: str | None,
) -> float | None:
    if experimental_population is not None:
        return float(experimental_population)
    if experimental_population_raw == "[0-3]":
        return MASKED_POPULATION_ESTIMATE
    return None


def _grid_cell_polygon_ring(
    *,
    northing_m: int,
    easting_m: int,
    grid_resolution_m: int,
) -> list[list[float]]:
    corners = [
        (easting_m, northing_m),
        (easting_m + grid_resolution_m, northing_m),
        (easting_m + grid_resolution_m, northing_m + grid_resolution_m),
        (easting_m, northing_m + grid_resolution_m),
        (easting_m, northing_m),
    ]
    ring: list[list[float]] = []
    for easting, northing in corners:
        lon, lat = GRID_TO_WGS84.transform(easting, northing)
        ring.append(
            [
                round(float(lon), POPULATION_COORD_PRECISION),
                round(float(lat), POPULATION_COORD_PRECISION),
            ]
        )
    return ring


def query_population_grid_cells(
    *,
    session,
    dataset_year: int,
    min_lat: float | None = None,
    min_lon: float | None = None,
    max_lat: float | None = None,
    max_lon: float | None = None,
) -> list[PopulationGridCellRecord]:
    provided_bounds = [min_lat, min_lon, max_lat, max_lon]
    if any(value is not None for value in provided_bounds) and any(
        value is None for value in provided_bounds
    ):
        raise ValueError("Population grid bounds must include min/max lat and lon.")
    if (
        min_lat is not None
        and max_lat is not None
        and min_lat > max_lat
        or min_lon is not None
        and max_lon is not None
        and min_lon > max_lon
    ):
        raise ValueError("Population grid bounds must be ordered min <= max.")

    query = (
        session.query(
            PopulationGridCell.grid_cell_id,
            PopulationGridCell.northing_m,
            PopulationGridCell.easting_m,
            PopulationGridCell.grid_resolution_m,
            PopulationGridCell.experimental_population,
            PopulationGridCell.experimental_population_raw,
            PopulationGridCell.plausibility_label,
        )
        .filter(PopulationGridCell.dataset_year == dataset_year)
        .filter(PopulationGridCell.cell_center_lat.isnot(None))
        .filter(PopulationGridCell.cell_center_lon.isnot(None))
    )
    if min_lat is not None:
        query = query.filter(PopulationGridCell.cell_center_lat >= min_lat)
        query = query.filter(PopulationGridCell.cell_center_lat <= max_lat)
        query = query.filter(PopulationGridCell.cell_center_lon >= min_lon)
        query = query.filter(PopulationGridCell.cell_center_lon <= max_lon)

    cells: list[PopulationGridCellRecord] = []
    for (
        grid_cell_id,
        northing_m,
        easting_m,
        grid_resolution_m,
        experimental_population,
        experimental_population_raw,
        plausibility_label,
    ) in query.all():
        if (
            grid_cell_id is None
            or northing_m is None
            or easting_m is None
            or grid_resolution_m is None
        ):
            continue
        population_estimate = estimate_population(
            experimental_population=(
                int(experimental_population)
                if experimental_population is not None
                else None
            ),
            experimental_population_raw=experimental_population_raw,
        )
        if population_estimate is None or population_estimate <= 0:
            continue
        cells.append(
            PopulationGridCellRecord(
                grid_cell_id=str(grid_cell_id),
                northing_m=int(northing_m),
                easting_m=int(easting_m),
                grid_resolution_m=int(grid_resolution_m),
                population_estimate=population_estimate,
                population_raw=experimental_population_raw,
                plausibility_label=plausibility_label,
            )
        )
    return cells


def build_population_grid_feature_collection(
    cells: list[PopulationGridCellRecord],
) -> dict[str, Any]:
    features: list[PopulationGridCellFeature] = []
    for cell in cells:
        features.append(
            PopulationGridCellFeature(
                ring_coordinates=_grid_cell_polygon_ring(
                    northing_m=cell.northing_m,
                    easting_m=cell.easting_m,
                    grid_resolution_m=cell.grid_resolution_m,
                ),
                population_estimate=cell.population_estimate,
            )
        )

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "population_estimate": feature.population_estimate,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [feature.ring_coordinates],
                },
            }
            for feature in features
        ],
    }


def load_population_grid_geojson(
    *,
    session,
    dataset_year: int,
    min_lat: float | None = None,
    min_lon: float | None = None,
    max_lat: float | None = None,
    max_lon: float | None = None,
) -> dict[str, Any]:
    source_cells = query_population_grid_cells(
        session=session,
        dataset_year=dataset_year,
        min_lat=min_lat,
        min_lon=min_lon,
        max_lat=max_lat,
        max_lon=max_lon,
    )
    return build_population_grid_feature_collection(source_cells)
