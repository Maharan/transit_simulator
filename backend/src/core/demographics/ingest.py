from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd
from pyproj import Transformer
from sqlalchemy import create_engine, delete, insert, text

from .models import PopulationGridCell


TITLE_SHEET_NAME = "Titelseite"
GRID_RESOLUTION_M = 1000
GRID_CELL_CENTER_OFFSET_M = GRID_RESOLUTION_M // 2
GRID_CRS_EPSG = 3035
WGS84_CRS_EPSG = 4326
YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
GRID_ID_PATTERN = re.compile(r"N(?P<northing>\d+)E(?P<easting>\d+)$")
GRID_TO_WGS84 = Transformer.from_crs(
    f"EPSG:{GRID_CRS_EPSG}",
    f"EPSG:{WGS84_CRS_EPSG}",
    always_xy=True,
)
SOURCE_COLUMN_MAP = {
    "Gitter-ID": "grid_cell_id",
    "AGS": "ags",
    "Gemeinde": "municipality_name",
    "Bezeichnung": "municipality_type",
    "Kreis": "district_name",
    "Bundesland": "state_name",
    "Einwohnerzahl_pro_Gemeinde": "municipality_population",
    "Exp_georef_BFS_20": "experimental_population_raw",
    "Plausibilisierung": "plausibility_label",
}


def _normalize_optional_str(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = str(value).strip()
    return normalized or None


def _find_data_sheet_name(sheet_names: list[str]) -> str:
    for sheet_name in sheet_names:
        if sheet_name != TITLE_SHEET_NAME:
            return sheet_name
    raise ValueError("Workbook does not contain a population-grid data sheet.")


def parse_population_grid_coordinates(grid_cell_id: str) -> tuple[int, int]:
    match = GRID_ID_PATTERN.search(grid_cell_id)
    if not match:
        raise ValueError(f"Unsupported population grid cell id: {grid_cell_id}")
    return int(match.group("northing")), int(match.group("easting"))


def project_population_grid_cell_center_to_wgs84(
    northing_m: int, easting_m: int
) -> tuple[float, float]:
    center_easting_m = easting_m + GRID_CELL_CENTER_OFFSET_M
    center_northing_m = northing_m + GRID_CELL_CENTER_OFFSET_M
    lon, lat = GRID_TO_WGS84.transform(center_easting_m, center_northing_m)
    return lat, lon


def infer_population_grid_year(workbook_path: Path) -> int:
    title_frame = pd.read_excel(
        workbook_path,
        sheet_name=TITLE_SHEET_NAME,
        header=None,
        engine="openpyxl",
        nrows=40,
    )
    for row in title_frame.itertuples(index=False):
        values = [value for value in row if value is not None and not pd.isna(value)]
        row_text = " ".join(str(value) for value in values)
        if "Datenstand/Berichtsjahr" in row_text:
            for value in reversed(values):
                if isinstance(value, (int, float)) and not pd.isna(value):
                    return int(value)
                match = YEAR_PATTERN.search(str(value))
                if match:
                    return int(match.group(0))

    flattened = title_frame.astype(str).stack()
    for value in flattened:
        match = YEAR_PATTERN.search(value)
        if match:
            return int(match.group(0))
    raise ValueError(f"Could not infer dataset year from {workbook_path}.")


def find_population_grid_workbook(root_dir: Path, dataset_year: int = 2020) -> Path:
    matches: list[Path] = []
    for workbook_path in sorted(Path(root_dir).rglob("*.xlsx")):
        try:
            workbook_year = infer_population_grid_year(workbook_path)
        except ValueError:
            continue
        if workbook_year == dataset_year:
            matches.append(workbook_path)

    if not matches:
        raise FileNotFoundError(
            f"No population grid workbook found for dataset year {dataset_year} in {root_dir}."
        )
    if len(matches) > 1:
        joined = ", ".join(str(path) for path in matches)
        raise ValueError(
            f"Multiple population grid workbooks found for dataset year {dataset_year}: {joined}"
        )
    return matches[0]


def load_population_grid_frame(
    workbook_path: Path,
    *,
    dataset_year: int | None = None,
) -> pd.DataFrame:
    workbook_path = Path(workbook_path)
    inferred_year = infer_population_grid_year(workbook_path)
    if dataset_year is None:
        dataset_year = inferred_year
    elif dataset_year != inferred_year:
        raise ValueError(
            f"Requested dataset year {dataset_year} does not match workbook year {inferred_year}."
        )

    excel_file = pd.ExcelFile(workbook_path, engine="openpyxl")
    data_sheet = _find_data_sheet_name(excel_file.sheet_names)
    frame = pd.read_excel(
        workbook_path,
        sheet_name=data_sheet,
        engine="openpyxl",
        dtype=str,
    )

    missing_columns = sorted(set(SOURCE_COLUMN_MAP) - set(frame.columns))
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(
            f"Workbook {workbook_path} is missing expected columns: {missing}"
        )

    frame = frame.rename(columns=SOURCE_COLUMN_MAP)
    frame = frame[list(SOURCE_COLUMN_MAP.values())].copy()

    for column_name in frame.columns:
        if column_name in {"municipality_population", "experimental_population_raw"}:
            continue
        frame[column_name] = frame[column_name].map(_normalize_optional_str)

    coordinates = frame["grid_cell_id"].map(parse_population_grid_coordinates)
    frame["northing_m"] = coordinates.map(lambda item: item[0]).astype("Int64")
    frame["easting_m"] = coordinates.map(lambda item: item[1]).astype("Int64")
    lat_lon = [
        project_population_grid_cell_center_to_wgs84(northing, easting)
        for northing, easting in coordinates
    ]
    frame["cell_center_lat"] = [item[0] for item in lat_lon]
    frame["cell_center_lon"] = [item[1] for item in lat_lon]

    frame["municipality_population"] = pd.to_numeric(
        frame["municipality_population"], errors="coerce"
    ).astype("Int64")
    frame["experimental_population_raw"] = frame["experimental_population_raw"].map(
        _normalize_optional_str
    )
    frame["experimental_population"] = pd.to_numeric(
        frame["experimental_population_raw"], errors="coerce"
    ).astype("Int64")
    frame["dataset_year"] = dataset_year
    frame["grid_resolution_m"] = GRID_RESOLUTION_M
    frame["source_path"] = str(workbook_path)
    frame["source_sheet"] = data_sheet

    ordered_columns = [
        "dataset_year",
        "grid_resolution_m",
        "grid_cell_id",
        "northing_m",
        "easting_m",
        "cell_center_lat",
        "cell_center_lon",
        "ags",
        "municipality_name",
        "municipality_type",
        "district_name",
        "state_name",
        "municipality_population",
        "experimental_population_raw",
        "experimental_population",
        "plausibility_label",
        "source_path",
        "source_sheet",
    ]
    return frame[ordered_columns]


def _iter_chunks(
    records: list[dict[str, object]], chunk_size: int
) -> Iterable[list[dict[str, object]]]:
    for start in range(0, len(records), chunk_size):
        yield records[start : start + chunk_size]


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    sanitized = frame.astype(object).where(pd.notna(frame), None)
    return sanitized.to_dict(orient="records")


def _create_schema(engine, schema: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))


def ingest_population_grid_workbook(
    workbook_path: Path,
    *,
    database_url: str,
    dataset_year: int = 2020,
    chunk_size: int = 10_000,
    replace_existing: bool = False,
    dry_run: bool = False,
    progress: bool = False,
    progress_every: int = 10,
) -> int:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    frame = load_population_grid_frame(workbook_path, dataset_year=dataset_year)
    row_count = len(frame)
    if dry_run:
        if progress:
            print(
                f"[population-grid:{dataset_year}] dry run: {row_count} rows from {workbook_path}"
            )
        return row_count

    engine = create_engine(database_url)
    schema = PopulationGridCell.__table__.schema
    if schema is None:
        raise RuntimeError("Population grid table schema must be defined.")
    _create_schema(engine, schema)
    PopulationGridCell.__table__.create(engine, checkfirst=True)

    records = _frame_to_records(frame)

    with engine.begin() as connection:
        if replace_existing:
            connection.execute(
                delete(PopulationGridCell).where(
                    PopulationGridCell.dataset_year == dataset_year
                )
            )
        for chunk_index, chunk in enumerate(_iter_chunks(records, chunk_size), start=1):
            connection.execute(insert(PopulationGridCell), chunk)
            if progress and (chunk_index == 1 or chunk_index % progress_every == 0):
                print(
                    f"[population-grid:{dataset_year}] loaded "
                    f"{min(chunk_index * chunk_size, row_count)} / {row_count} rows"
                )

    if progress:
        print(f"[population-grid:{dataset_year}] complete ({row_count} rows)")
    return row_count
