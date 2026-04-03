from __future__ import annotations

from sqlalchemy import Float, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.gtfs.models import Base
from infra.postgis import PostGISGeometry


class HamburgLod1Building(Base):
    __tablename__ = "hh_buildings_lod1"
    __table_args__ = (
        UniqueConstraint(
            "dataset_release",
            "gml_id",
            name="uq_hh_buildings_lod1_dataset_release_gml_id",
        ),
        Index(
            "ix_built_environment_hh_buildings_lod1_footprint_geom",
            "footprint_geom",
            postgresql_using="gist",
        ),
        {"schema": "built_environment"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_release: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tile_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    gml_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    building_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    function_code: Mapped[str | None] = mapped_column(String, nullable=True)
    municipality_code: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    street_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    street_number: Mapped[str | None] = mapped_column(String, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    locality_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_name: Mapped[str | None] = mapped_column(String, nullable=True)
    measured_height_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    storeys_above_ground: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ground_elevation_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    roof_elevation_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    representative_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    representative_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_attributes: Mapped[dict[str, str | None] | None] = mapped_column(
        JSON, nullable=True
    )
    source_srs_name: Mapped[str] = mapped_column(String, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    footprint_geom: Mapped[str] = mapped_column(
        PostGISGeometry("MULTIPOLYGON", 25832),
        nullable=False,
    )


class HamburgFloorSpaceCell(Base):
    __tablename__ = "hh_floor_space_grid"
    __table_args__ = (
        UniqueConstraint(
            "dataset_release",
            "grid_resolution_m",
            "cell_easting_m",
            "cell_northing_m",
            name="uq_hh_floor_space_grid_dataset_release_resolution_cell",
        ),
        Index(
            "ix_built_environment_hh_floor_space_grid_center_geom",
            "center_geom",
            postgresql_using="gist",
        ),
        {"schema": "built_environment"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_release: Mapped[str] = mapped_column(String, nullable=False, index=True)
    grid_resolution_m: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cell_easting_m: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cell_northing_m: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    building_count: Mapped[int] = mapped_column(Integer, nullable=False)
    footprint_area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    floor_space_m2: Mapped[float] = mapped_column(Float, nullable=False)
    floor_space_density_sqkm: Mapped[float] = mapped_column(Float, nullable=False)
    population_estimate: Mapped[float] = mapped_column(Float, nullable=False)
    population_density_sqkm: Mapped[float] = mapped_column(Float, nullable=False)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    center_lon: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    center_geom: Mapped[str] = mapped_column(
        PostGISGeometry("POINT", 4326),
        nullable=False,
    )
