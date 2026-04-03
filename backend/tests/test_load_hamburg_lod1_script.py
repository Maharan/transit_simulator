from __future__ import annotations

from pathlib import Path

import pytest

import scripts.load_hamburg_lod1 as load_hamburg_lod1


def test_parser_defaults_target_hamburg_release() -> None:
    args = load_hamburg_lod1._build_parser().parse_args([])

    assert args.dataset_release == "2023-04-01"
    assert args.chunk_size == 1_000
    assert args.replace_existing is False


def test_main_discovers_dataset_dir_and_calls_ingest(monkeypatch, capsys) -> None:
    monkeypatch.setattr(load_hamburg_lod1, "load_dotenv", lambda **_kwargs: None)
    monkeypatch.setenv("DATABASE_URL_LOCAL", "postgresql://example")

    dataset_dir = Path("files") / "LoD1-DE_HH_2023-04-01"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        load_hamburg_lod1,
        "find_hamburg_lod1_dataset_dir",
        lambda root_dir, dataset_release: dataset_dir,
    )

    def _fake_ingest(**kwargs):
        captured.update(kwargs)
        return 456

    monkeypatch.setattr(
        load_hamburg_lod1,
        "ingest_hamburg_lod1_directory",
        _fake_ingest,
    )

    load_hamburg_lod1.main(["--dataset-release", "2023-04-01", "--replace-existing"])
    output = capsys.readouterr().out.strip()

    assert captured == {
        "dataset_dir": dataset_dir,
        "database_url": "postgresql://example",
        "dataset_release": "2023-04-01",
        "chunk_size": 1_000,
        "replace_existing": True,
        "dry_run": False,
        "progress": True,
        "progress_every": 25,
    }
    assert output == (f"Ingested Hamburg LoD1 2023-04-01: 456 rows from {dataset_dir}")


def test_main_rejects_missing_database_url(monkeypatch) -> None:
    monkeypatch.setattr(load_hamburg_lod1, "load_dotenv", lambda **_kwargs: None)
    monkeypatch.delenv("DATABASE_URL_LOCAL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(
        SystemExit, match="DATABASE_URL_LOCAL or DATABASE_URL must be set"
    ):
        load_hamburg_lod1.main([])
