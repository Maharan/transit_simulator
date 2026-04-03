from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))


def _build_parser(
    *,
    default_dataset_release: str,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load Hamburg LoD1 building footprints into Postgres."
    )
    parser.add_argument(
        "--dataset-release",
        default=default_dataset_release,
        help=(
            "Hamburg LoD1 dataset release to load "
            f"(default: {default_dataset_release})."
        ),
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Optional explicit dataset directory. Defaults to auto-discovery by release.",
    )
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=Path(os.environ.get("HAMBURG_LOD1_ROOT", "files")),
        help="Root directory to search for Hamburg LoD1 folders (default: files).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1_000,
        help="Rows to insert per batch (default: 1000).",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete existing rows for the dataset release before inserting new ones.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse the XML files and report how many buildings would be loaded.",
    )
    parser.add_argument(
        "--progress",
        default=True,
        action="store_true",
        help="Print file-level progress while loading.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="How often to print progress by file (default: 25).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    from core.built_environment import (
        DEFAULT_HAMBURG_LOD1_DATASET_RELEASE,
        find_hamburg_lod1_dataset_dir,
        ingest_hamburg_lod1_directory,
    )

    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")
    args = _build_parser(
        default_dataset_release=DEFAULT_HAMBURG_LOD1_DATASET_RELEASE,
    ).parse_args(argv)

    database_url = os.environ.get("DATABASE_URL_LOCAL") or os.environ.get(
        "DATABASE_URL"
    )
    if not database_url:
        raise SystemExit(
            "DATABASE_URL_LOCAL or DATABASE_URL must be set in the environment."
        )

    dataset_dir = args.dataset_dir
    if dataset_dir is None:
        dataset_dir = find_hamburg_lod1_dataset_dir(
            args.root_dir,
            dataset_release=args.dataset_release,
        )
    elif not dataset_dir.exists():
        raise SystemExit(f"Hamburg LoD1 dataset directory not found: {dataset_dir}")

    row_count = ingest_hamburg_lod1_directory(
        dataset_dir=dataset_dir,
        database_url=database_url,
        dataset_release=args.dataset_release,
        chunk_size=args.chunk_size,
        replace_existing=args.replace_existing,
        dry_run=args.dry_run,
        progress=args.progress,
        progress_every=args.progress_every,
    )

    if args.dry_run:
        print(
            f"Dry run complete for Hamburg LoD1 {args.dataset_release}: "
            f"{row_count} rows from {dataset_dir}"
        )
    else:
        print(
            f"Ingested Hamburg LoD1 {args.dataset_release}: "
            f"{row_count} rows from {dataset_dir}"
        )


if __name__ == "__main__":
    main()
