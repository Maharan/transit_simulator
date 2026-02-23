from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from core.server.route_service import RouteService
from scripts import route_server


def main(argv: list[str] | None = None) -> None:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")
    args = route_server._build_parser().parse_args(argv)
    if args.skip_preload:
        raise SystemExit(
            "--skip-preload is not supported in preload_graph_cache.py. "
            "Remove it or run scripts/route_server.py instead."
        )

    service = RouteService(args)
    logs = service.preload(rebuild=args.rebuild_on_start)
    for line in logs:
        print(line)


if __name__ == "__main__":
    main()
