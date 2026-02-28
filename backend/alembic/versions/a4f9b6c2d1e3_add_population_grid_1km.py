"""add population grid 1km table

Revision ID: a4f9b6c2d1e3
Revises: 5f87e01acc7d
Create Date: 2026-02-28 18:10:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a4f9b6c2d1e3"
down_revision = "5f87e01acc7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS demographics")
    op.create_table(
        "population_grid_1km",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_year", sa.Integer(), nullable=False),
        sa.Column("grid_resolution_m", sa.Integer(), nullable=False),
        sa.Column("grid_cell_id", sa.String(), nullable=False),
        sa.Column("ags", sa.String(), nullable=True),
        sa.Column("municipality_name", sa.Text(), nullable=True),
        sa.Column("municipality_type", sa.String(), nullable=True),
        sa.Column("district_name", sa.Text(), nullable=True),
        sa.Column("state_name", sa.String(), nullable=True),
        sa.Column("municipality_population", sa.Integer(), nullable=True),
        sa.Column("experimental_population_raw", sa.String(), nullable=True),
        sa.Column("experimental_population", sa.Integer(), nullable=True),
        sa.Column("plausibility_label", sa.String(), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_sheet", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_year",
            "grid_cell_id",
            name="uq_population_grid_1km_dataset_year_grid_cell_id",
        ),
        schema="demographics",
    )
    op.create_index(
        op.f("ix_demographics_population_grid_1km_ags"),
        "population_grid_1km",
        ["ags"],
        unique=False,
        schema="demographics",
    )
    op.create_index(
        op.f("ix_demographics_population_grid_1km_dataset_year"),
        "population_grid_1km",
        ["dataset_year"],
        unique=False,
        schema="demographics",
    )
    op.create_index(
        op.f("ix_demographics_population_grid_1km_grid_cell_id"),
        "population_grid_1km",
        ["grid_cell_id"],
        unique=False,
        schema="demographics",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_demographics_population_grid_1km_grid_cell_id"),
        table_name="population_grid_1km",
        schema="demographics",
    )
    op.drop_index(
        op.f("ix_demographics_population_grid_1km_dataset_year"),
        table_name="population_grid_1km",
        schema="demographics",
    )
    op.drop_index(
        op.f("ix_demographics_population_grid_1km_ags"),
        table_name="population_grid_1km",
        schema="demographics",
    )
    op.drop_table("population_grid_1km", schema="demographics")
