from __future__ import annotations

from sqlalchemy import create_engine, delete, text

from .ingest import (
    DEFAULT_HAMBURG_LOD1_DATASET_RELEASE,
    _ensure_postgis_and_schema,
)
from .models import HamburgFloorSpaceCell


DEFAULT_FLOOR_SPACE_GRID_RESOLUTION_M = 100
DEFAULT_HAMBURG_TOTAL_POPULATION = 1_850_000.0
DEFAULT_STOREY_HEIGHT_M = 3.2


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
    if grid_resolution_m <= 0:
        raise ValueError("grid_resolution_m must be greater than zero.")
    if total_population <= 0:
        raise ValueError("total_population must be greater than zero.")
    if default_storey_height_m <= 0:
        raise ValueError("default_storey_height_m must be greater than zero.")

    engine = create_engine(database_url)
    _ensure_postgis_and_schema(engine)
    HamburgFloorSpaceCell.__table__.create(engine, checkfirst=True)

    with engine.begin() as connection:
        if replace_existing:
            connection.execute(
                delete(HamburgFloorSpaceCell).where(
                    HamburgFloorSpaceCell.dataset_release == dataset_release,
                    HamburgFloorSpaceCell.grid_resolution_m == grid_resolution_m,
                )
            )

        inserted_count = connection.execute(
            text(
                """
                WITH building_weights AS (
                    SELECT
                        b.dataset_release,
                        floor(ST_X(ST_PointOnSurface(b.footprint_geom)) / :grid_resolution_m)
                            * :grid_resolution_m AS cell_easting_m,
                        floor(ST_Y(ST_PointOnSurface(b.footprint_geom)) / :grid_resolution_m)
                            * :grid_resolution_m AS cell_northing_m,
                        ST_Area(b.footprint_geom) AS footprint_area_m2,
                        ST_Area(b.footprint_geom) * GREATEST(
                            1.0,
                            COALESCE(
                                NULLIF(b.storeys_above_ground, 0)::double precision,
                                ROUND(b.measured_height_m / :default_storey_height_m),
                                1.0
                            )
                        ) AS floor_space_m2
                    FROM built_environment.hh_buildings_lod1 AS b
                    WHERE b.dataset_release = :dataset_release
                ),
                aggregates AS (
                    SELECT
                        dataset_release,
                        cell_easting_m::integer AS cell_easting_m,
                        cell_northing_m::integer AS cell_northing_m,
                        COUNT(*)::integer AS building_count,
                        SUM(footprint_area_m2)::double precision AS footprint_area_m2,
                        SUM(floor_space_m2)::double precision AS floor_space_m2
                    FROM building_weights
                    GROUP BY dataset_release, cell_easting_m, cell_northing_m
                ),
                totals AS (
                    SELECT COALESCE(SUM(floor_space_m2), 0.0) AS total_floor_space_m2
                    FROM aggregates
                ),
                inserted AS (
                    INSERT INTO built_environment.hh_floor_space_grid (
                        dataset_release,
                        grid_resolution_m,
                        cell_easting_m,
                        cell_northing_m,
                        building_count,
                        footprint_area_m2,
                        floor_space_m2,
                        floor_space_density_sqkm,
                        population_estimate,
                        population_density_sqkm,
                        center_lat,
                        center_lon,
                        center_geom
                    )
                    SELECT
                        :dataset_release,
                        :grid_resolution_m,
                        a.cell_easting_m,
                        a.cell_northing_m,
                        a.building_count,
                        a.footprint_area_m2,
                        a.floor_space_m2,
                        a.floor_space_m2 * 1000000.0
                            / (:grid_resolution_m * :grid_resolution_m),
                        CASE
                            WHEN t.total_floor_space_m2 > 0
                            THEN :total_population * a.floor_space_m2 / t.total_floor_space_m2
                            ELSE 0.0
                        END AS population_estimate,
                        CASE
                            WHEN t.total_floor_space_m2 > 0
                            THEN (
                                :total_population * a.floor_space_m2 / t.total_floor_space_m2
                            ) * 1000000.0 / (:grid_resolution_m * :grid_resolution_m)
                            ELSE 0.0
                        END AS population_density_sqkm,
                        ST_Y(
                            ST_Transform(
                                ST_SetSRID(
                                    ST_MakePoint(
                                        a.cell_easting_m + (:grid_resolution_m / 2.0),
                                        a.cell_northing_m + (:grid_resolution_m / 2.0)
                                    ),
                                    25832
                                ),
                                4326
                            )
                        ) AS center_lat,
                        ST_X(
                            ST_Transform(
                                ST_SetSRID(
                                    ST_MakePoint(
                                        a.cell_easting_m + (:grid_resolution_m / 2.0),
                                        a.cell_northing_m + (:grid_resolution_m / 2.0)
                                    ),
                                    25832
                                ),
                                4326
                            )
                        ) AS center_lon,
                        ST_Transform(
                            ST_SetSRID(
                                ST_MakePoint(
                                    a.cell_easting_m + (:grid_resolution_m / 2.0),
                                    a.cell_northing_m + (:grid_resolution_m / 2.0)
                                ),
                                25832
                            ),
                            4326
                        ) AS center_geom
                    FROM aggregates AS a
                    CROSS JOIN totals AS t
                    WHERE a.floor_space_m2 > 0
                    RETURNING 1
                )
                SELECT COUNT(*) FROM inserted
                """
            ),
            {
                "dataset_release": dataset_release,
                "grid_resolution_m": grid_resolution_m,
                "total_population": float(total_population),
                "default_storey_height_m": float(default_storey_height_m),
            },
        ).scalar_one()

    if progress:
        print(
            f"[floor-space-grid:{dataset_release}:{grid_resolution_m}m] "
            f"complete ({inserted_count} cells)"
        )
    return int(inserted_count)
