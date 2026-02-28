from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.demographics.ingest import (
    find_population_grid_workbook,
    infer_population_grid_year,
    load_population_grid_frame,
    parse_population_grid_coordinates,
    project_population_grid_cell_center_to_wgs84,
)


def _write_population_grid_workbook(path: Path, dataset_year: int) -> None:
    title_rows = [[None, None, None, None] for _ in range(15)]
    title_rows.append([None, "Datenstand/Berichtsjahr:", None, dataset_year])
    title_rows.extend([[None, None, None, None] for _ in range(3)])
    title_frame = pd.DataFrame(title_rows)
    data_frame = pd.DataFrame(
        {
            "Gitter-ID": [
                "CRS3035RES1kmN2725000E4321000",
                "CRS3035RES1kmN2726000E4322000",
            ],
            "AGS": ["02000000", "02000001"],
            "Gemeinde": ["Hamburg", "Ahrensburg"],
            "Bezeichnung": ["Gemeinde", "Gemeinde"],
            "Kreis": ["Hamburg", "Stormarn"],
            "Bundesland": ["Hamburg", "Schleswig-Holstein"],
            "Einwohnerzahl_pro_Gemeinde": ["100", "200"],
            "Exp_georef_BFS_20": ["[0-3]", "7"],
            "Plausibilisierung": ["plausibel", "unplausibel"],
        }
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        title_frame.to_excel(writer, sheet_name="Titelseite", header=False, index=False)
        data_frame.to_excel(
            writer,
            sheet_name="Bevölkerungsraster (1km x 1 km)",
            header=True,
            index=False,
        )


def test_infer_population_grid_year_reads_title_sheet(tmp_path: Path) -> None:
    workbook_path = tmp_path / "population_2020.xlsx"
    _write_population_grid_workbook(workbook_path, dataset_year=2020)

    assert infer_population_grid_year(workbook_path) == 2020


def test_find_population_grid_workbook_selects_requested_year(tmp_path: Path) -> None:
    workbook_2019 = tmp_path / "population_2019.xlsx"
    workbook_2020 = tmp_path / "population_2020.xlsx"
    _write_population_grid_workbook(workbook_2019, dataset_year=2019)
    _write_population_grid_workbook(workbook_2020, dataset_year=2020)

    assert find_population_grid_workbook(tmp_path, dataset_year=2020) == workbook_2020


def test_load_population_grid_frame_maps_columns_and_preserves_masked_values(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "population_2020.xlsx"
    _write_population_grid_workbook(workbook_path, dataset_year=2020)

    frame = load_population_grid_frame(workbook_path, dataset_year=2020)

    assert list(frame.columns) == [
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
    assert frame.to_dict(orient="records") == [
        {
            "dataset_year": 2020,
            "grid_resolution_m": 1000,
            "grid_cell_id": "CRS3035RES1kmN2725000E4321000",
            "northing_m": 2725000,
            "easting_m": 4321000,
            "cell_center_lat": frame.iloc[0]["cell_center_lat"],
            "cell_center_lon": frame.iloc[0]["cell_center_lon"],
            "ags": "02000000",
            "municipality_name": "Hamburg",
            "municipality_type": "Gemeinde",
            "district_name": "Hamburg",
            "state_name": "Hamburg",
            "municipality_population": 100,
            "experimental_population_raw": "[0-3]",
            "experimental_population": None,
            "plausibility_label": "plausibel",
            "source_path": str(workbook_path),
            "source_sheet": "Bevölkerungsraster (1km x 1 km)",
        },
        {
            "dataset_year": 2020,
            "grid_resolution_m": 1000,
            "grid_cell_id": "CRS3035RES1kmN2726000E4322000",
            "northing_m": 2726000,
            "easting_m": 4322000,
            "cell_center_lat": frame.iloc[1]["cell_center_lat"],
            "cell_center_lon": frame.iloc[1]["cell_center_lon"],
            "ags": "02000001",
            "municipality_name": "Ahrensburg",
            "municipality_type": "Gemeinde",
            "district_name": "Stormarn",
            "state_name": "Schleswig-Holstein",
            "municipality_population": 200,
            "experimental_population_raw": "7",
            "experimental_population": 7,
            "plausibility_label": "unplausibel",
            "source_path": str(workbook_path),
            "source_sheet": "Bevölkerungsraster (1km x 1 km)",
        },
    ]


def test_parse_population_grid_coordinates_extracts_projected_values() -> None:
    assert parse_population_grid_coordinates("CRS3035RES1kmN2725000E4321000") == (
        2725000,
        4321000,
    )


def test_parse_population_grid_coordinates_rejects_invalid_ids() -> None:
    try:
        parse_population_grid_coordinates("CELL-1")
    except ValueError as exc:
        assert "Unsupported population grid cell id" in str(exc)
    else:
        raise AssertionError("Expected invalid grid ids to raise ValueError")


def test_project_population_grid_cell_center_to_wgs84_returns_germany_like_point() -> (
    None
):
    lat, lon = project_population_grid_cell_center_to_wgs84(2725000, 4321000)

    assert 47.0 < lat < 48.5
    assert 9.0 < lon < 11.5
