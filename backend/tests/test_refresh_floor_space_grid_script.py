from __future__ import annotations

import pytest

import scripts.refresh_floor_space_grid as refresh_floor_space_grid


def test_parser_defaults_target_hamburg_floor_space_grid() -> None:
    args = refresh_floor_space_grid._build_parser().parse_args([])

    assert args.dataset_release == "2023-04-01"
    assert args.grid_resolution_m == 100
    assert args.total_population == 1_850_000.0
    assert args.replace_existing is False


def test_main_calls_refresh(monkeypatch, capsys) -> None:
    monkeypatch.setattr(refresh_floor_space_grid, "load_dotenv", lambda **_kwargs: None)
    monkeypatch.setenv("DATABASE_URL_LOCAL", "postgresql://example")

    captured: dict[str, object] = {}

    def _fake_refresh(**kwargs):
        captured.update(kwargs)
        return 789

    monkeypatch.setattr(
        refresh_floor_space_grid,
        "refresh_hamburg_floor_space_grid",
        _fake_refresh,
    )

    refresh_floor_space_grid.main(
        [
            "--dataset-release",
            "2023-04-01",
            "--grid-resolution-m",
            "100",
            "--replace-existing",
        ]
    )
    output = capsys.readouterr().out.strip()

    assert captured == {
        "database_url": "postgresql://example",
        "dataset_release": "2023-04-01",
        "grid_resolution_m": 100,
        "total_population": 1_850_000.0,
        "default_storey_height_m": 3.2,
        "replace_existing": True,
        "progress": True,
    }
    assert output == "Refreshed Hamburg floor-space grid 2023-04-01 at 100m: 789 cells"


def test_main_rejects_missing_database_url(monkeypatch) -> None:
    monkeypatch.setattr(refresh_floor_space_grid, "load_dotenv", lambda **_kwargs: None)
    monkeypatch.delenv("DATABASE_URL_LOCAL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(
        SystemExit, match="DATABASE_URL_LOCAL or DATABASE_URL must be set"
    ):
        refresh_floor_space_grid.main([])
