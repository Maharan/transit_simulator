"""add population grid wgs84 cell center

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-02-28 19:10:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pyproj import Transformer


revision = "c7d8e9f0a1b2"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None

GRID_CELL_CENTER_OFFSET_M = 500
GRID_TO_WGS84 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)


def upgrade() -> None:
    op.add_column(
        "population_grid_1km",
        sa.Column("cell_center_lat", sa.Float(), nullable=True),
        schema="demographics",
    )
    op.add_column(
        "population_grid_1km",
        sa.Column("cell_center_lon", sa.Float(), nullable=True),
        schema="demographics",
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, northing_m, easting_m
            FROM demographics.population_grid_1km
            WHERE northing_m IS NOT NULL AND easting_m IS NOT NULL
            """
        )
    ).fetchall()

    updates: list[dict[str, float | int]] = []
    for row in rows:
        lon, lat = GRID_TO_WGS84.transform(
            row.easting_m + GRID_CELL_CENTER_OFFSET_M,
            row.northing_m + GRID_CELL_CENTER_OFFSET_M,
        )
        updates.append(
            {
                "id": row.id,
                "cell_center_lat": lat,
                "cell_center_lon": lon,
            }
        )

    if updates:
        bind.execute(
            sa.text(
                """
                UPDATE demographics.population_grid_1km
                SET
                    cell_center_lat = :cell_center_lat,
                    cell_center_lon = :cell_center_lon
                WHERE id = :id
                """
            ),
            updates,
        )


def downgrade() -> None:
    op.drop_column("population_grid_1km", "cell_center_lon", schema="demographics")
    op.drop_column("population_grid_1km", "cell_center_lat", schema="demographics")
