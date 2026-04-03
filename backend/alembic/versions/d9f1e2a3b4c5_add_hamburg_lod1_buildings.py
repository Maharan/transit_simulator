"""add Hamburg LoD1 buildings

Revision ID: d9f1e2a3b4c5
Revises: c7d8e9f0a1b2
Create Date: 2026-04-03 16:15:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d9f1e2a3b4c5"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE SCHEMA IF NOT EXISTS built_environment")
    op.create_table(
        "hh_buildings_lod1",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_release", sa.String(), nullable=False),
        sa.Column("tile_id", sa.String(), nullable=False),
        sa.Column("gml_id", sa.String(), nullable=False),
        sa.Column("building_name", sa.Text(), nullable=True),
        sa.Column("function_code", sa.String(), nullable=True),
        sa.Column("municipality_code", sa.String(), nullable=True),
        sa.Column("street_name", sa.Text(), nullable=True),
        sa.Column("street_number", sa.String(), nullable=True),
        sa.Column("postal_code", sa.String(), nullable=True),
        sa.Column("locality_name", sa.Text(), nullable=True),
        sa.Column("country_name", sa.String(), nullable=True),
        sa.Column("measured_height_m", sa.Float(), nullable=True),
        sa.Column("storeys_above_ground", sa.Integer(), nullable=True),
        sa.Column("ground_elevation_m", sa.Float(), nullable=True),
        sa.Column("roof_elevation_m", sa.Float(), nullable=True),
        sa.Column("representative_lat", sa.Float(), nullable=True),
        sa.Column("representative_lon", sa.Float(), nullable=True),
        sa.Column("raw_attributes", sa.JSON(), nullable=True),
        sa.Column("source_srs_name", sa.String(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_release",
            "gml_id",
            name="uq_hh_buildings_lod1_dataset_release_gml_id",
        ),
        schema="built_environment",
    )
    op.execute(
        """
        ALTER TABLE built_environment.hh_buildings_lod1
        ADD COLUMN footprint_geom geometry(MultiPolygon,25832) NOT NULL
        """
    )
    op.create_index(
        op.f("ix_built_environment_hh_buildings_lod1_dataset_release"),
        "hh_buildings_lod1",
        ["dataset_release"],
        unique=False,
        schema="built_environment",
    )
    op.create_index(
        op.f("ix_built_environment_hh_buildings_lod1_tile_id"),
        "hh_buildings_lod1",
        ["tile_id"],
        unique=False,
        schema="built_environment",
    )
    op.create_index(
        op.f("ix_built_environment_hh_buildings_lod1_gml_id"),
        "hh_buildings_lod1",
        ["gml_id"],
        unique=False,
        schema="built_environment",
    )
    op.create_index(
        op.f("ix_built_environment_hh_buildings_lod1_municipality_code"),
        "hh_buildings_lod1",
        ["municipality_code"],
        unique=False,
        schema="built_environment",
    )
    op.create_index(
        op.f("ix_built_environment_hh_buildings_lod1_postal_code"),
        "hh_buildings_lod1",
        ["postal_code"],
        unique=False,
        schema="built_environment",
    )
    op.execute(
        """
        CREATE INDEX ix_built_environment_hh_buildings_lod1_footprint_geom
        ON built_environment.hh_buildings_lod1
        USING GIST (footprint_geom)
        """
    )
    op.create_table(
        "hh_floor_space_grid",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_release", sa.String(), nullable=False),
        sa.Column("grid_resolution_m", sa.Integer(), nullable=False),
        sa.Column("cell_easting_m", sa.Integer(), nullable=False),
        sa.Column("cell_northing_m", sa.Integer(), nullable=False),
        sa.Column("building_count", sa.Integer(), nullable=False),
        sa.Column("footprint_area_m2", sa.Float(), nullable=False),
        sa.Column("floor_space_m2", sa.Float(), nullable=False),
        sa.Column("floor_space_density_sqkm", sa.Float(), nullable=False),
        sa.Column("population_estimate", sa.Float(), nullable=False),
        sa.Column("population_density_sqkm", sa.Float(), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lon", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_release",
            "grid_resolution_m",
            "cell_easting_m",
            "cell_northing_m",
            name="uq_hh_floor_space_grid_dataset_release_resolution_cell",
        ),
        schema="built_environment",
    )
    op.execute(
        """
        ALTER TABLE built_environment.hh_floor_space_grid
        ADD COLUMN center_geom geometry(Point,4326) NOT NULL
        """
    )
    op.create_index(
        op.f("ix_built_environment_hh_floor_space_grid_dataset_release"),
        "hh_floor_space_grid",
        ["dataset_release"],
        unique=False,
        schema="built_environment",
    )
    op.create_index(
        op.f("ix_built_environment_hh_floor_space_grid_grid_resolution_m"),
        "hh_floor_space_grid",
        ["grid_resolution_m"],
        unique=False,
        schema="built_environment",
    )
    op.create_index(
        op.f("ix_built_environment_hh_floor_space_grid_cell_easting_m"),
        "hh_floor_space_grid",
        ["cell_easting_m"],
        unique=False,
        schema="built_environment",
    )
    op.create_index(
        op.f("ix_built_environment_hh_floor_space_grid_cell_northing_m"),
        "hh_floor_space_grid",
        ["cell_northing_m"],
        unique=False,
        schema="built_environment",
    )
    op.create_index(
        op.f("ix_built_environment_hh_floor_space_grid_center_lat"),
        "hh_floor_space_grid",
        ["center_lat"],
        unique=False,
        schema="built_environment",
    )
    op.create_index(
        op.f("ix_built_environment_hh_floor_space_grid_center_lon"),
        "hh_floor_space_grid",
        ["center_lon"],
        unique=False,
        schema="built_environment",
    )
    op.execute(
        """
        CREATE INDEX ix_built_environment_hh_floor_space_grid_center_geom
        ON built_environment.hh_floor_space_grid
        USING GIST (center_geom)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS "
        "built_environment.ix_built_environment_hh_floor_space_grid_center_geom"
    )
    op.drop_index(
        op.f("ix_built_environment_hh_floor_space_grid_center_lon"),
        table_name="hh_floor_space_grid",
        schema="built_environment",
    )
    op.drop_index(
        op.f("ix_built_environment_hh_floor_space_grid_center_lat"),
        table_name="hh_floor_space_grid",
        schema="built_environment",
    )
    op.drop_index(
        op.f("ix_built_environment_hh_floor_space_grid_cell_northing_m"),
        table_name="hh_floor_space_grid",
        schema="built_environment",
    )
    op.drop_index(
        op.f("ix_built_environment_hh_floor_space_grid_cell_easting_m"),
        table_name="hh_floor_space_grid",
        schema="built_environment",
    )
    op.drop_index(
        op.f("ix_built_environment_hh_floor_space_grid_grid_resolution_m"),
        table_name="hh_floor_space_grid",
        schema="built_environment",
    )
    op.drop_index(
        op.f("ix_built_environment_hh_floor_space_grid_dataset_release"),
        table_name="hh_floor_space_grid",
        schema="built_environment",
    )
    op.drop_table("hh_floor_space_grid", schema="built_environment")
    op.execute(
        "DROP INDEX IF EXISTS "
        "built_environment.ix_built_environment_hh_buildings_lod1_footprint_geom"
    )
    op.drop_index(
        op.f("ix_built_environment_hh_buildings_lod1_postal_code"),
        table_name="hh_buildings_lod1",
        schema="built_environment",
    )
    op.drop_index(
        op.f("ix_built_environment_hh_buildings_lod1_municipality_code"),
        table_name="hh_buildings_lod1",
        schema="built_environment",
    )
    op.drop_index(
        op.f("ix_built_environment_hh_buildings_lod1_gml_id"),
        table_name="hh_buildings_lod1",
        schema="built_environment",
    )
    op.drop_index(
        op.f("ix_built_environment_hh_buildings_lod1_tile_id"),
        table_name="hh_buildings_lod1",
        schema="built_environment",
    )
    op.drop_index(
        op.f("ix_built_environment_hh_buildings_lod1_dataset_release"),
        table_name="hh_buildings_lod1",
        schema="built_environment",
    )
    op.drop_table("hh_buildings_lod1", schema="built_environment")
