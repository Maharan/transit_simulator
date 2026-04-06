from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
import uvicorn

from core.graph.caching import DEFAULT_GRAPH_METHOD, SUPPORTED_GRAPH_METHODS
from core.server import RouteService, build_fastapi_app


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a long-lived HTTP route planner that keeps transit graphs warm "
            "in memory."
        )
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--feed-id",
        default="Upload__hvv_Rohdaten_GTFS_Fpl_20241209",
        help="Default feed_id used when route requests omit feed_id.",
    )
    parser.add_argument(
        "--depart-time",
        default="09:00:00",
        help="Default departure time as HH:MM:SS.",
    )
    parser.add_argument(
        "--transfer-penalty",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--route-change-penalty",
        type=int,
        default=0,
        help=(
            "Extra penalty in seconds when switching routes/trips beyond explicit "
            "transfer times from GTFS transfers.txt (default: 0)."
        ),
    )
    parser.add_argument(
        "--heuristic-max-speed-mps",
        type=float,
        default=55.0,
    )
    parser.add_argument(
        "--state-by",
        choices=["route", "trip"],
        default="route",
    )
    parser.add_argument(
        "--time-horizon-sec",
        type=int,
        default=4 * 3600,
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=8,
        help="Maximum RAPTOR rounds / transit boardings (default: 8).",
    )
    parser.add_argument(
        "--max-major-transfers",
        type=int,
        default=4,
        help=(
            "Maximum major transit transfers for RAPTOR alternatives "
            "(walking links do not count; default: 4)."
        ),
    )
    parser.add_argument("--disable-walking", action="store_true")
    parser.add_argument("--walk-max-distance-m", type=int, default=500)
    parser.add_argument("--walk-speed-mps", type=float, default=0.7)
    parser.add_argument("--walk-max-neighbors", type=int, default=10)
    parser.add_argument("--coord-max-candidates", type=int, default=6)
    parser.add_argument("--coord-max-distance-m", type=float, default=500.0)
    parser.add_argument(
        "--graph-cache",
        default=".cache/graph.pkl",
        help="Pickle path used for cold-start fallback (default: .cache/graph.pkl).",
    )
    parser.add_argument("--symmetric-transfers", action="store_true")
    parser.add_argument(
        "--graph-method",
        choices=SUPPORTED_GRAPH_METHODS,
        default=DEFAULT_GRAPH_METHOD,
        help="Graph implementation used for routing (default: trip_stop).",
    )
    parser.add_argument(
        "--anytime-default-headway-sec",
        type=int,
        default=None,
        help="Fallback headway for trip_stop_anytime when route headway is unknown.",
    )
    parser.add_argument("--graph-cache-version", type=int, default=8)
    parser.add_argument(
        "--rebuild-on-start",
        action="store_true",
        help="Rebuild graph cache from GTFS tables before accepting requests.",
    )
    parser.add_argument(
        "--skip-preload",
        action="store_true",
        help="Skip warm-loading graph at startup.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print progress while (re)building graph data.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=5000,
        help="How often to print progress counters (default: 5000).",
    )
    return parser


def main() -> None:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")
    args = _build_parser().parse_args()
    service = RouteService(args)

    if not args.skip_preload:
        logs = service.preload(rebuild=args.rebuild_on_start)
        for line in logs:
            print(line)

    app = build_fastapi_app(service)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
