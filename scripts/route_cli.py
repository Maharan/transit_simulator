from __future__ import annotations

import argparse
import cProfile
import pstats
from pathlib import Path

from dotenv import load_dotenv
from graph.caching import access_or_create_graph_cache
from graph.utils import resolve_parent_stop
from gtfs.utils import resolve_feed_id, resolve_stop_by_name
from user_facing.itinerary import create_itinerary, create_itinerary_data
from routing.td_dijkstra import td_dijkstra
from routing.utils import parse_time_to_seconds
from gtfs.models import Stop
from infra import Database


def main() -> None:
    graph_cache_version = 5
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(
        description="Compute travel time between two stops using cached graph edges."
    )
    parser.add_argument("from_stop", help="Stop name (exact or partial match).")
    parser.add_argument("to_stop", help="Stop name (exact or partial match).")
    parser.add_argument(
        "--from-stop-id",
        help="Use a specific from stop_id instead of resolving by name.",
    )
    parser.add_argument(
        "--to-stop-id",
        help="Use a specific to stop_id instead of resolving by name.",
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
    args = parser.parse_args()

    profiler: cProfile.Profile | None = None
    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()

    try:
        session = Database().session()
        feed_id = resolve_feed_id(session, args.feed_id)

        if args.from_stop_id:
            row = (
                session.query(Stop.stop_id, Stop.stop_name)
                .filter(Stop.feed_id == feed_id)
                .filter(Stop.stop_id == args.from_stop_id)
                .first()
            )
            if not row:
                raise SystemExit(f"Unknown from stop_id: {args.from_stop_id}")
            from_stop_id, from_stop_name = row[0], row[1] or row[0]
        else:
            from_stop_id, from_stop_name = resolve_stop_by_name(
                session, feed_id, args.from_stop
            )

        if args.to_stop_id:
            row = (
                session.query(Stop.stop_id, Stop.stop_name)
                .filter(Stop.feed_id == feed_id)
                .filter(Stop.stop_id == args.to_stop_id)
                .first()
            )
            if not row:
                raise SystemExit(f"Unknown to stop_id: {args.to_stop_id}")
            to_stop_id, to_stop_name = row[0], row[1] or row[0]
        else:
            to_stop_id, to_stop_name = resolve_stop_by_name(
                session, feed_id, args.to_stop
            )

        depart_time_sec = parse_time_to_seconds(args.depart_time)
        if depart_time_sec is None:
            raise SystemExit("Invalid --depart-time. Expected HH:MM:SS.")

        from_parent_id, from_parent_name = resolve_parent_stop(
            session, feed_id, from_stop_id
        )
        to_parent_id, to_parent_name = resolve_parent_stop(session, feed_id, to_stop_id)
        from_stop_name = from_parent_name or from_stop_name
        to_stop_name = to_parent_name or to_stop_name

        cache_path = Path(args.graph_cache) if args.graph_cache else None
        rebuild_cache = args.rebuild or args.rebuild_graph_cache
        graph, cache_logs = access_or_create_graph_cache(
            session=session,
            feed_id=feed_id,
            cache_path=cache_path,
            graph_cache_version=graph_cache_version,
            rebuild_cache=rebuild_cache,
            symmetric_transfers=args.symmetric_transfers,
        )
        for line in cache_logs:
            print(line)

        result = td_dijkstra(
            graph=graph,
            start_id=from_parent_id,
            goal_id=to_parent_id,
            depart_time_str=args.depart_time,
            assume_zero_missing=args.assume_zero_missing,
            transfer_penalty_sec=args.transfer_penalty,
            route_change_penalty_sec=args.route_change_penalty,
            time_horizon_sec=args.time_horizon_sec,
            state_by=args.state_by,
        )

        if result.arrival_time_sec is None:
            raise SystemExit(
                f"No path found from '{from_stop_name}' to '{to_stop_name}'."
            )

        stop_names, route_short_names = create_itinerary_data(
            session=session,
            feed_id=feed_id,
            stop_ids=result.stop_path,
        )
        itinerary = create_itinerary(
            result=result,
            from_stop_name=from_stop_name,
            to_stop_name=to_stop_name,
            depart_time_str=args.depart_time,
            stop_names=stop_names,
            route_short_names=route_short_names,
            transfer_penalty_sec=args.transfer_penalty,
        )
        for line in itinerary.lines():
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
