from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from core.built_environment import (  # noqa: E402
    DEFAULT_FLOOR_SPACE_GRID_RESOLUTION_M,
    DEFAULT_HAMBURG_LOD1_DATASET_RELEASE,
    DEFAULT_HAMBURG_TOTAL_POPULATION,
    refresh_hamburg_floor_space_grid,
)


def _build_parser(
    *,
    default_dataset_release: str = DEFAULT_HAMBURG_LOD1_DATASET_RELEASE,
    default_grid_resolution_m: int = DEFAULT_FLOOR_SPACE_GRID_RESOLUTION_M,
    default_total_population: float = DEFAULT_HAMBURG_TOTAL_POPULATION,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a gridded Hamburg floor-space surface in Postgres."
    )
    parser.add_argument(
        "--dataset-release",
        default=default_dataset_release,
        help=(
            "Hamburg LoD1 dataset release to aggregate "
            f"(default: {default_dataset_release})."
        ),
    )
    parser.add_argument(
        "--grid-resolution-m",
        type=int,
        default=default_grid_resolution_m,
        help=(
            "Grid cell size in meters for the aggregated surface "
            f"(default: {default_grid_resolution_m})."
        ),
    )
    parser.add_argument(
        "--total-population",
        type=float,
        default=default_total_population,
        help=(
            "Population total used to scale floor-space weights "
            f"(default: {default_total_population})."
        ),
    )
    parser.add_argument(
        "--default-storey-height-m",
        type=float,
        default=3.2,
        help="Fallback storey height used when storeys are missing (default: 3.2).",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete existing rows for the dataset release and resolution before inserting.",
    )
    parser.add_argument(
        "--progress",
        default=True,
        action="store_true",
        help="Print a completion summary after refreshing the surface.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")
    args = _build_parser(
        default_dataset_release=DEFAULT_HAMBURG_LOD1_DATASET_RELEASE,
        default_grid_resolution_m=DEFAULT_FLOOR_SPACE_GRID_RESOLUTION_M,
        default_total_population=DEFAULT_HAMBURG_TOTAL_POPULATION,
    ).parse_args(argv)

    database_url = os.environ.get("DATABASE_URL_LOCAL") or os.environ.get(
        "DATABASE_URL"
    )
    if not database_url:
        raise SystemExit(
            "DATABASE_URL_LOCAL or DATABASE_URL must be set in the environment."
        )

    row_count = refresh_hamburg_floor_space_grid(
        database_url=database_url,
        dataset_release=args.dataset_release,
        grid_resolution_m=args.grid_resolution_m,
        total_population=args.total_population,
        default_storey_height_m=args.default_storey_height_m,
        replace_existing=args.replace_existing,
        progress=args.progress,
    )

    print(
        f"Refreshed Hamburg floor-space grid {args.dataset_release} "
        f"at {args.grid_resolution_m}m: {row_count} cells"
    )


if __name__ == "__main__":
    main()
