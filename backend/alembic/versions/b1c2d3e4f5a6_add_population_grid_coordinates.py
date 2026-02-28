"""add population grid coordinates

Revision ID: b1c2d3e4f5a6
Revises: a4f9b6c2d1e3
Create Date: 2026-02-28 18:45:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a6"
down_revision = "a4f9b6c2d1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "population_grid_1km",
        sa.Column("northing_m", sa.Integer(), nullable=True),
        schema="demographics",
    )
    op.add_column(
        "population_grid_1km",
        sa.Column("easting_m", sa.Integer(), nullable=True),
        schema="demographics",
    )
    op.create_index(
        op.f("ix_demographics_population_grid_1km_northing_m"),
        "population_grid_1km",
        ["northing_m"],
        unique=False,
        schema="demographics",
    )
    op.create_index(
        op.f("ix_demographics_population_grid_1km_easting_m"),
        "population_grid_1km",
        ["easting_m"],
        unique=False,
        schema="demographics",
    )
    op.execute(
        """
        UPDATE demographics.population_grid_1km
        SET
            northing_m = NULLIF(substring(grid_cell_id FROM 'N([0-9]+)E'), '')::integer,
            easting_m = NULLIF(substring(grid_cell_id FROM 'E([0-9]+)$'), '')::integer
        WHERE grid_cell_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_demographics_population_grid_1km_easting_m"),
        table_name="population_grid_1km",
        schema="demographics",
    )
    op.drop_index(
        op.f("ix_demographics_population_grid_1km_northing_m"),
        table_name="population_grid_1km",
        schema="demographics",
    )
    op.drop_column("population_grid_1km", "easting_m", schema="demographics")
    op.drop_column("population_grid_1km", "northing_m", schema="demographics")
