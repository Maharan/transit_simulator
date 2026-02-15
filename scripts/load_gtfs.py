from __future__ import annotations

import os
from pathlib import Path

from gtfs import ingest_all_gtfs


def main() -> None:
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

    ingest_all_gtfs(root_dir=root_dir, database_url=database_url)
    print(f"Ingested GTFS feeds from {root_dir}")


if __name__ == "__main__":
    main()
