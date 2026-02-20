from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from gtfs import ingest_all_gtfs


def main() -> None:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Load GTFS feeds into Postgres.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate GTFS files and print planned tables without writing to the DB.",
    )
    parser.add_argument(
        "--progress",
        default=True,
        action="store_true",
        help="Print table-level progress while loading.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="How often to print progress by chunk (default: 10).",
    )
    parser.add_argument(
        "--skip-table",
        action="append",
        default=[],
        help="Table name to skip (e.g., shapes). Can be provided multiple times.",
    )
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="Drop existing tables in the schema before re-creating them.",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL_LOCAL") or os.environ.get(
        "DATABASE_URL"
    )
    if not database_url:
        raise SystemExit(
            "DATABASE_URL_LOCAL or DATABASE_URL must be set in the environment."
        )

    root_dir = Path(os.environ.get("GTFS_ROOT", "files"))
    if not root_dir.exists():
        raise SystemExit(f"GTFS root folder not found: {root_dir}")

    ingest_all_gtfs(
        root_dir=root_dir,
        database_url=database_url,
        dry_run=args.dry_run,
        progress=args.progress,
        progress_every=args.progress_every,
        skip_tables=set(args.skip_table),
        drop_existing=args.drop_existing,
    )
    if args.dry_run:
        print(f"Dry run complete for GTFS feeds in {root_dir}")
    else:
        print(f"Ingested GTFS feeds from {root_dir}")


if __name__ == "__main__":
    main()
