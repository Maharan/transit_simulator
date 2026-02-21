from __future__ import annotations

import argparse
import cProfile
import pstats
from pathlib import Path

from dotenv import load_dotenv

from core.routing.route_planner import (
    RoutePlannerRequest,
    find_best_route_and_itinerary,
)
from infra import Database


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute travel time between two stops using cached graph edges."
    )
    parser.add_argument(
        "from_stop",
        nargs="?",
        help="From stop name (exact or partial match).",
    )
    parser.add_argument(
        "to_stop",
        nargs="?",
        help="To stop name (exact or partial match).",
    )
    parser.add_argument(
        "--from-stop-id",
        help="Use a specific from stop_id instead of resolving by name.",
    )
    parser.add_argument(
        "--to-stop-id",
        help="Use a specific to stop_id instead of resolving by name.",
    )
    parser.add_argument(
        "--from-lat",
        type=float,
        help="From latitude. Must be paired with --from-lon.",
    )
    parser.add_argument(
        "--from-lon",
        type=float,
        help="From longitude. Must be paired with --from-lat.",
    )
    parser.add_argument(
        "--to-lat",
        type=float,
        help="To latitude. Must be paired with --to-lon.",
    )
    parser.add_argument(
        "--to-lon",
        type=float,
        help="To longitude. Must be paired with --to-lat.",
    )
    parser.add_argument(
        "--coord-max-candidates",
        type=int,
        default=6,
        help="How many nearby coordinate stop candidates to evaluate (default: 6).",
    )
    parser.add_argument(
        "--coord-max-distance-m",
        type=float,
        default=500.0,
        help="Max distance from coordinate to candidate stop in meters (default: 500).",
    )
    parser.add_argument(
        "--feed-id",
        default="Upload__hvv_Rohdaten_GTFS_Fpl_20241209",
        help="GTFS feed_id to use. Required if multiple feeds exist.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild graph cache from GTFS tables.",
    )
    parser.add_argument(
        "--assume-zero-missing",
        action="store_true",
        help="Treat missing edge weights as 0 seconds.",
    )
    parser.add_argument(
        "--depart-time",
        default="09:00:00",
        help="Departure time as HH:MM:SS (default: 09:00:00).",
    )
    parser.add_argument(
        "--transfer-penalty",
        type=int,
        default=300,
        help="Penalty in seconds added to each transfer (default: 300).",
    )
    parser.add_argument(
        "--route-change-penalty",
        type=int,
        default=None,
        help="Penalty in seconds when switching trips at the same stop "
        "(default: transfer penalty).",
    )
    parser.add_argument(
        "--state-by",
        choices=["route", "trip"],
        default="route",
        help="Track state by route_id or trip_id (default: route).",
    )
    parser.add_argument(
        "--time-horizon-sec",
        type=int,
        default=4 * 3600,
        help="Ignore departures after depart_time + horizon (default: 14400).",
    )
    parser.add_argument(
        "--disable-walking",
        action="store_true",
        help="Disable synthetic walking transfer edges between nearby stops.",
    )
    parser.add_argument(
        "--walk-max-distance-m",
        type=int,
        default=500,
        help="Maximum walking link distance in meters (default: 500).",
    )
    parser.add_argument(
        "--walk-speed-mps",
        type=float,
        default=0.7,
        # Lower than typical 1.4 m/s to compensate for indirect pedestrian paths.
        help="Walking speed in meters/sec used to estimate walk time (default: 0.7).",
    )
    parser.add_argument(
        "--walk-max-neighbors",
        type=int,
        default=10,
        help="Maximum synthetic walking neighbors per stop (default: 10).",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Run cProfile and print a summary of the slowest functions.",
    )
    parser.add_argument(
        "--profile-sort",
        default="cumtime",
        help="Sort key for profiling stats (default: cumtime).",
    )
    parser.add_argument(
        "--profile-top",
        type=int,
        default=40,
        help="How many profiling lines to print (default: 40).",
    )
    parser.add_argument(
        "--profile-output",
        help="Optional path to write a .pstats file.",
    )
    parser.add_argument(
        "--graph-cache",
        help="Path to a pickle file used to cache the in-memory graph.",
    )
    parser.add_argument(
        "--rebuild-graph-cache",
        action="store_true",
        help="Rebuild and overwrite the pickle graph cache if --graph-cache is set.",
    )
    parser.add_argument(
        "--symmetric-transfers",
        action="store_true",
        help="Treat transfers as bidirectional edges.",
    )
    return parser


def main() -> None:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    args = _build_parser().parse_args()

    profiler: cProfile.Profile | None = None
    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()

    try:
        session = Database().session()
        result = find_best_route_and_itinerary(
            session=session,
            request=RoutePlannerRequest(
                from_stop_name=args.from_stop,
                to_stop_name=args.to_stop,
                from_stop_id=args.from_stop_id,
                to_stop_id=args.to_stop_id,
                from_lat=args.from_lat,
                from_lon=args.from_lon,
                to_lat=args.to_lat,
                to_lon=args.to_lon,
                coord_max_candidates=args.coord_max_candidates,
                coord_max_distance_m=args.coord_max_distance_m,
                feed_id=args.feed_id,
                rebuild=args.rebuild,
                assume_zero_missing=args.assume_zero_missing,
                depart_time=args.depart_time,
                transfer_penalty_sec=args.transfer_penalty,
                route_change_penalty_sec=args.route_change_penalty,
                state_by=args.state_by,
                time_horizon_sec=args.time_horizon_sec,
                disable_walking=args.disable_walking,
                walk_max_distance_m=args.walk_max_distance_m,
                walk_speed_mps=args.walk_speed_mps,
                walk_max_neighbors=args.walk_max_neighbors,
                graph_cache_path=Path(args.graph_cache) if args.graph_cache else None,
                rebuild_graph_cache=args.rebuild_graph_cache,
                symmetric_transfers=args.symmetric_transfers,
            ),
        )
        for line in result.cache_logs:
            print(line)
        for line in result.context_lines:
            print(line)
        for line in result.itinerary.lines():
            print(line)
    finally:
        if profiler:
            profiler.disable()
            if args.profile_output:
                pstats.Stats(profiler).dump_stats(args.profile_output)
            stats = pstats.Stats(profiler).sort_stats(args.profile_sort)
            print("\nProfile summary:")
            stats.print_stats(args.profile_top)


if __name__ == "__main__":
    main()
