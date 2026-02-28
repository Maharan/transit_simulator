from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.gtfs.models import Base


class PopulationGridCell(Base):
    __tablename__ = "population_grid_1km"
    __table_args__ = (
        UniqueConstraint(
            "dataset_year",
            "grid_cell_id",
            name="uq_population_grid_1km_dataset_year_grid_cell_id",
        ),
        {"schema": "demographics"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    grid_resolution_m: Mapped[int] = mapped_column(Integer, nullable=False)
    grid_cell_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    northing_m: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    easting_m: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    cell_center_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    cell_center_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    ags: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    municipality_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    municipality_type: Mapped[str | None] = mapped_column(String, nullable=True)
    district_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_name: Mapped[str | None] = mapped_column(String, nullable=True)
    municipality_population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experimental_population_raw: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    experimental_population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plausibility_label: Mapped[str | None] = mapped_column(String, nullable=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_sheet: Mapped[str] = mapped_column(String, nullable=False)
