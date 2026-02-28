from __future__ import annotations

from pathlib import Path

import pytest

import scripts.load_population_grid as load_population_grid


def test_parser_defaults_target_2020_workbook() -> None:
    args = load_population_grid._build_parser().parse_args([])

    assert args.dataset_year == 2020
    assert args.chunk_size == 10_000
    assert args.replace_existing is False


def test_main_discovers_workbook_and_calls_ingest(monkeypatch, capsys) -> None:
    monkeypatch.setattr(load_population_grid, "load_dotenv", lambda **_kwargs: None)
    monkeypatch.setenv("DATABASE_URL_LOCAL", "postgresql://example")

    workbook_path = Path("files") / "population_2020.xlsx"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        load_population_grid,
        "find_population_grid_workbook",
        lambda root_dir, dataset_year: workbook_path,
    )

    def _fake_ingest(**kwargs):
        captured.update(kwargs)
        return 123

    monkeypatch.setattr(
        load_population_grid, "ingest_population_grid_workbook", _fake_ingest
    )

    load_population_grid.main(["--dataset-year", "2020", "--replace-existing"])
    output = capsys.readouterr().out.strip()

    assert captured == {
        "workbook_path": workbook_path,
        "database_url": "postgresql://example",
        "dataset_year": 2020,
        "chunk_size": 10_000,
        "replace_existing": True,
        "dry_run": False,
        "progress": True,
        "progress_every": 10,
    }
    assert output == f"Ingested population grid 2020: 123 rows from {workbook_path}"


def test_main_rejects_missing_database_url(monkeypatch) -> None:
    monkeypatch.setattr(load_population_grid, "load_dotenv", lambda **_kwargs: None)
    monkeypatch.delenv("DATABASE_URL_LOCAL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(
        SystemExit, match="DATABASE_URL_LOCAL or DATABASE_URL must be set"
    ):
        load_population_grid.main([])
