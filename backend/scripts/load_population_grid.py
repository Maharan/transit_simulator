from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from core.demographics import (
    find_population_grid_workbook,
    ingest_population_grid_workbook,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load Destatis population grid rows into Postgres."
    )
    parser.add_argument(
        "--dataset-year",
        type=int,
        default=2020,
        help="Dataset year to load from backend/files (default: 2020).",
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=None,
        help="Optional explicit workbook path. Defaults to auto-discovery by dataset year.",
    )
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=Path(os.environ.get("POPULATION_GRID_ROOT", "files")),
        help="Root directory to search for workbook files (default: files).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=10_000,
        help="Rows to insert per batch (default: 10000).",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete existing rows for the dataset year before inserting new ones.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read the workbook and report how many rows would be loaded without writing.",
    )
    parser.add_argument(
        "--progress",
        default=True,
        action="store_true",
        help="Print batch progress while loading.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="How often to print progress by batch (default: 10).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")
    args = _build_parser().parse_args(argv)

    database_url = os.environ.get("DATABASE_URL_LOCAL") or os.environ.get(
        "DATABASE_URL"
    )
    if not database_url:
        raise SystemExit(
            "DATABASE_URL_LOCAL or DATABASE_URL must be set in the environment."
        )

    workbook_path = args.workbook
    if workbook_path is None:
        if not args.root_dir.exists():
            raise SystemExit(f"Population grid root folder not found: {args.root_dir}")
        workbook_path = find_population_grid_workbook(
            args.root_dir, dataset_year=args.dataset_year
        )
    elif not workbook_path.exists():
        raise SystemExit(f"Population grid workbook not found: {workbook_path}")

    row_count = ingest_population_grid_workbook(
        workbook_path=workbook_path,
        database_url=database_url,
        dataset_year=args.dataset_year,
        chunk_size=args.chunk_size,
        replace_existing=args.replace_existing,
        dry_run=args.dry_run,
        progress=args.progress,
        progress_every=args.progress_every,
    )

    if args.dry_run:
        print(
            f"Dry run complete for population grid {args.dataset_year}: "
            f"{row_count} rows from {workbook_path}"
        )
    else:
        print(
            f"Ingested population grid {args.dataset_year}: "
            f"{row_count} rows from {workbook_path}"
        )


if __name__ == "__main__":
    main()
