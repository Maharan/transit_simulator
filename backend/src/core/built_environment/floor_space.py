from __future__ import annotations

from sqlalchemy import (
    Float,
    Integer,
    bindparam,
    case,
    cast,
    create_engine,
    delete,
    func,
    insert,
    literal,
    select,
    true,
)

from .ingest import (
    DEFAULT_HAMBURG_LOD1_DATASET_RELEASE,
    _ensure_postgis_and_schema,
)
from .models import HamburgFloorSpaceCell, HamburgLod1Building


DEFAULT_FLOOR_SPACE_GRID_RESOLUTION_M = 100
DEFAULT_HAMBURG_TOTAL_POPULATION = 1_850_000.0
DEFAULT_STOREY_HEIGHT_M = 3.2
HAMBURG_BUILDING_EPSG = 25832
WGS84_EPSG = 4326
SQUARE_METERS_PER_SQUARE_KILOMETER = 1_000_000.0


def _validate_floor_space_inputs(
    *,
    grid_resolution_m: int,
    total_population: float,
    default_storey_height_m: float,
) -> None:
    if grid_resolution_m <= 0:
        raise ValueError("grid_resolution_m must be greater than zero.")
    if total_population <= 0:
        raise ValueError("total_population must be greater than zero.")
    if default_storey_height_m <= 0:
        raise ValueError("default_storey_height_m must be greater than zero.")


def _build_floor_space_refresh_count_statement():
    buildings = HamburgLod1Building.__table__
    floor_space_grid = HamburgFloorSpaceCell.__table__

    dataset_release_param = bindparam("dataset_release")
    grid_resolution_param = bindparam("grid_resolution_m")
    total_population_param = bindparam("total_population")
    default_storey_height_param = bindparam("default_storey_height_m")

    grid_resolution_float = cast(grid_resolution_param, Float)
    half_grid_resolution = grid_resolution_float / 2.0
    cell_area_m2 = grid_resolution_float * grid_resolution_float

    point_on_surface = func.ST_PointOnSurface(buildings.c.footprint_geom)
    footprint_area_m2 = func.ST_Area(buildings.c.footprint_geom)
    inferred_storeys = func.greatest(
        1.0,
        func.coalesce(
            cast(func.nullif(buildings.c.storeys_above_ground, 0), Float),
            cast(
                func.round(buildings.c.measured_height_m / default_storey_height_param),
                Float,
            ),
            1.0,
        ),
    )

    building_weights = (
        select(
            buildings.c.dataset_release.label("dataset_release"),
            cast(
                func.floor(func.ST_X(point_on_surface) / grid_resolution_float)
                * grid_resolution_float,
                Integer,
            ).label("cell_easting_m"),
            cast(
                func.floor(func.ST_Y(point_on_surface) / grid_resolution_float)
                * grid_resolution_float,
                Integer,
            ).label("cell_northing_m"),
            footprint_area_m2.label("footprint_area_m2"),
            (footprint_area_m2 * inferred_storeys).label("floor_space_m2"),
        )
        .where(buildings.c.dataset_release == dataset_release_param)
        .cte("building_weights")
    )

    aggregates = (
        select(
            building_weights.c.dataset_release,
            cast(building_weights.c.cell_easting_m, Integer).label("cell_easting_m"),
            cast(building_weights.c.cell_northing_m, Integer).label("cell_northing_m"),
            cast(func.count(), Integer).label("building_count"),
            cast(
                func.sum(building_weights.c.footprint_area_m2),
                Float,
            ).label("footprint_area_m2"),
            cast(
                func.sum(building_weights.c.floor_space_m2),
                Float,
            ).label("floor_space_m2"),
        )
        .group_by(
            building_weights.c.dataset_release,
            building_weights.c.cell_easting_m,
            building_weights.c.cell_northing_m,
        )
        .cte("aggregates")
    )

    totals = (
        select(
            func.coalesce(
                func.sum(aggregates.c.floor_space_m2),
                0.0,
            ).label("total_floor_space_m2")
        )
        .select_from(aggregates)
        .cte("totals")
    )

    center_geom = func.ST_Transform(
        func.ST_SetSRID(
            func.ST_MakePoint(
                cast(aggregates.c.cell_easting_m, Float) + half_grid_resolution,
                cast(aggregates.c.cell_northing_m, Float) + half_grid_resolution,
            ),
            HAMBURG_BUILDING_EPSG,
        ),
        WGS84_EPSG,
    )
    floor_space_density_sqkm = (
        aggregates.c.floor_space_m2 * SQUARE_METERS_PER_SQUARE_KILOMETER / cell_area_m2
    )
    population_estimate = case(
        (
            totals.c.total_floor_space_m2 > 0,
            total_population_param
            * aggregates.c.floor_space_m2
            / totals.c.total_floor_space_m2,
        ),
        else_=0.0,
    )
    population_density_sqkm = case(
        (
            totals.c.total_floor_space_m2 > 0,
            population_estimate * SQUARE_METERS_PER_SQUARE_KILOMETER / cell_area_m2,
        ),
        else_=0.0,
    )

    insert_query = (
        select(
            dataset_release_param,
            grid_resolution_param,
            aggregates.c.cell_easting_m,
            aggregates.c.cell_northing_m,
            aggregates.c.building_count,
            aggregates.c.footprint_area_m2,
            aggregates.c.floor_space_m2,
            floor_space_density_sqkm.label("floor_space_density_sqkm"),
            population_estimate.label("population_estimate"),
            population_density_sqkm.label("population_density_sqkm"),
            func.ST_Y(center_geom).label("center_lat"),
            func.ST_X(center_geom).label("center_lon"),
            center_geom.label("center_geom"),
        )
        .select_from(aggregates.join(totals, true()))
        .where(aggregates.c.floor_space_m2 > 0)
    )

    inserted = (
        insert(floor_space_grid)
        .from_select(
            [
                floor_space_grid.c.dataset_release,
                floor_space_grid.c.grid_resolution_m,
                floor_space_grid.c.cell_easting_m,
                floor_space_grid.c.cell_northing_m,
                floor_space_grid.c.building_count,
                floor_space_grid.c.footprint_area_m2,
                floor_space_grid.c.floor_space_m2,
                floor_space_grid.c.floor_space_density_sqkm,
                floor_space_grid.c.population_estimate,
                floor_space_grid.c.population_density_sqkm,
                floor_space_grid.c.center_lat,
                floor_space_grid.c.center_lon,
                floor_space_grid.c.center_geom,
            ],
            insert_query,
        )
        .returning(literal(1).label("inserted"))
        .cte("inserted")
    )

    return select(func.count()).select_from(inserted)


def refresh_hamburg_floor_space_grid(
    *,
    database_url: str,
    dataset_release: str = DEFAULT_HAMBURG_LOD1_DATASET_RELEASE,
    grid_resolution_m: int = DEFAULT_FLOOR_SPACE_GRID_RESOLUTION_M,
    total_population: float = DEFAULT_HAMBURG_TOTAL_POPULATION,
    default_storey_height_m: float = DEFAULT_STOREY_HEIGHT_M,
    replace_existing: bool = False,
    progress: bool = False,
) -> int:
    _validate_floor_space_inputs(
        grid_resolution_m=grid_resolution_m,
        total_population=total_population,
        default_storey_height_m=default_storey_height_m,
    )

    engine = create_engine(database_url)
    _ensure_postgis_and_schema(engine)
    HamburgFloorSpaceCell.__table__.create(engine, checkfirst=True)

    refresh_count_statement = _build_floor_space_refresh_count_statement()
    query_params = {
        "dataset_release": dataset_release,
        "grid_resolution_m": grid_resolution_m,
        "total_population": float(total_population),
        "default_storey_height_m": float(default_storey_height_m),
    }

    with engine.begin() as connection:
        if replace_existing:
            connection.execute(
                delete(HamburgFloorSpaceCell).where(
                    HamburgFloorSpaceCell.dataset_release == dataset_release,
                    HamburgFloorSpaceCell.grid_resolution_m == grid_resolution_m,
                )
            )

        inserted_count = connection.execute(
            refresh_count_statement,
            query_params,
        ).scalar_one()

    if progress:
        print(
            f"[floor-space-grid:{dataset_release}:{grid_resolution_m}m] "
            f"complete ({inserted_count} cells)"
        )
    return int(inserted_count)
