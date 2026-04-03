from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.built_environment.models import HamburgFloorSpaceCell


@dataclass(frozen=True)
class FloorSpaceCellRecord:
    center_lat: float
    center_lon: float
    building_count: int
    floor_space_m2: float
    floor_space_density_sqkm: float
    population_estimate: float
    population_density_sqkm: float


def query_floor_space_cells(
    *,
    session,
    dataset_release: str,
    grid_resolution_m: int,
    min_lat: float | None = None,
    min_lon: float | None = None,
    max_lat: float | None = None,
    max_lon: float | None = None,
) -> list[FloorSpaceCellRecord]:
    provided_bounds = [min_lat, min_lon, max_lat, max_lon]
    if any(value is not None for value in provided_bounds) and any(
        value is None for value in provided_bounds
    ):
        raise ValueError("Floor-space density bounds must include min/max lat and lon.")
    if (
        min_lat is not None
        and max_lat is not None
        and min_lat > max_lat
        or min_lon is not None
        and max_lon is not None
        and min_lon > max_lon
    ):
        raise ValueError("Floor-space density bounds must be ordered min <= max.")

    query = (
        session.query(
            HamburgFloorSpaceCell.center_lat,
            HamburgFloorSpaceCell.center_lon,
            HamburgFloorSpaceCell.building_count,
            HamburgFloorSpaceCell.floor_space_m2,
            HamburgFloorSpaceCell.floor_space_density_sqkm,
            HamburgFloorSpaceCell.population_estimate,
            HamburgFloorSpaceCell.population_density_sqkm,
        )
        .filter(HamburgFloorSpaceCell.dataset_release == dataset_release)
        .filter(HamburgFloorSpaceCell.grid_resolution_m == grid_resolution_m)
    )
    if min_lat is not None:
        query = query.filter(HamburgFloorSpaceCell.center_lat >= min_lat)
        query = query.filter(HamburgFloorSpaceCell.center_lat <= max_lat)
        query = query.filter(HamburgFloorSpaceCell.center_lon >= min_lon)
        query = query.filter(HamburgFloorSpaceCell.center_lon <= max_lon)

    cells: list[FloorSpaceCellRecord] = []
    for (
        center_lat,
        center_lon,
        building_count,
        floor_space_m2,
        floor_space_density_sqkm,
        population_estimate,
        population_density_sqkm,
    ) in query.all():
        if (
            center_lat is None
            or center_lon is None
            or building_count is None
            or floor_space_m2 is None
            or floor_space_density_sqkm is None
            or population_estimate is None
            or population_density_sqkm is None
        ):
            continue
        cells.append(
            FloorSpaceCellRecord(
                center_lat=float(center_lat),
                center_lon=float(center_lon),
                building_count=int(building_count),
                floor_space_m2=float(floor_space_m2),
                floor_space_density_sqkm=float(floor_space_density_sqkm),
                population_estimate=float(population_estimate),
                population_density_sqkm=float(population_density_sqkm),
            )
        )
    return cells


def build_floor_space_feature_collection(
    cells: list[FloorSpaceCellRecord],
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "building_count": cell.building_count,
                    "floor_space_m2": cell.floor_space_m2,
                    "floor_space_density_sqkm": cell.floor_space_density_sqkm,
                    "population_estimate": cell.population_estimate,
                    "population_density_sqkm": cell.population_density_sqkm,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [cell.center_lon, cell.center_lat],
                },
            }
            for cell in cells
        ],
    }


def load_floor_space_density_geojson(
    *,
    session,
    dataset_release: str,
    grid_resolution_m: int,
    min_lat: float | None = None,
    min_lon: float | None = None,
    max_lat: float | None = None,
    max_lon: float | None = None,
) -> dict[str, Any]:
    cells = query_floor_space_cells(
        session=session,
        dataset_release=dataset_release,
        grid_resolution_m=grid_resolution_m,
        min_lat=min_lat,
        min_lon=min_lon,
        max_lat=max_lat,
        max_lon=max_lon,
    )
    return build_floor_space_feature_collection(cells)
