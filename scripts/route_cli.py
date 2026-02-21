from __future__ import annotations

import argparse
import pickle
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import func

from graph import GraphCache
from user_facing.itinerary import ItineraryBuilder
from routing.td_dijkstra import td_dijkstra
from routing.utils import parse_time_to_seconds
from gtfs.models import Route, Stop
from infra import Database


def _resolve_feed_id(session, requested_feed_id: str | None) -> str:
    if requested_feed_id:
        return requested_feed_id
    rows = session.query(Stop.feed_id).distinct().all()
    feed_ids = [row[0] for row in rows if row[0]]
    if len(feed_ids) == 1:
        return feed_ids[0]
    if not feed_ids:
        raise SystemExit("No feeds found in gtfs.stops.")
    raise SystemExit(
        "Multiple feeds found. Provide --feed-id. "
        f"Available: {', '.join(sorted(feed_ids))}"
    )


def _resolve_stop_by_name(session, feed_id: str, name: str) -> tuple[str, str]:
    normalized = name.strip().lower()
    if not normalized:
        raise SystemExit("Stop name cannot be empty.")

    exact = (
        session.query(Stop.stop_id, Stop.stop_name)
        .filter(Stop.feed_id == feed_id)
        .filter(Stop.stop_name.isnot(None))
        .filter(func.lower(Stop.stop_name) == normalized)
        .all()
    )
    if len(exact) == 1:
        return exact[0][0], exact[0][1]
    if len(exact) > 1:
        options = ", ".join(f"{row[1]} ({row[0]})" for row in exact[:10])
        raise SystemExit(
            f"Multiple stops match '{name}'. Be more specific. Examples: {options}"
        )

    like = (
        session.query(Stop.stop_id, Stop.stop_name)
        .filter(Stop.feed_id == feed_id)
        .filter(Stop.stop_name.isnot(None))
        .filter(func.lower(Stop.stop_name).like(f"%{normalized}%"))
        .all()
    )
    if len(like) == 1:
        return like[0][0], like[0][1]
    if not like:
        raise SystemExit(f"No stops found matching '{name}'.")
    options = ", ".join(f"{row[1]} ({row[0]})" for row in like[:10])
    raise SystemExit(
        f"Multiple stops match '{name}'. Be more specific. Examples: {options}"
    )


def main() -> None:
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

    session = Database().session()
    feed_id = _resolve_feed_id(session, args.feed_id)

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
        from_stop_id, from_stop_name = _resolve_stop_by_name(
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
        to_stop_id, to_stop_name = _resolve_stop_by_name(session, feed_id, args.to_stop)

    depart_time_sec = parse_time_to_seconds(args.depart_time)
    if depart_time_sec is None:
        raise SystemExit("Invalid --depart-time. Expected HH:MM:SS.")

    def _resolve_parent_stop(stop_id: str) -> tuple[str, str | None]:
        row = (
            session.query(Stop.stop_id, Stop.parent_station)
            .filter(Stop.feed_id == feed_id)
            .filter(Stop.stop_id == stop_id)
            .first()
        )
        if row and row[1]:
            parent_id = row[1]
            parent_name_row = (
                session.query(Stop.stop_name)
                .filter(Stop.feed_id == feed_id)
                .filter(Stop.stop_id == parent_id)
                .first()
            )
            return parent_id, parent_name_row[0] if parent_name_row else parent_id
        return stop_id, None

    from_parent_id, from_parent_name = _resolve_parent_stop(from_stop_id)
    to_parent_id, to_parent_name = _resolve_parent_stop(to_stop_id)
    from_stop_name = from_parent_name or from_stop_name
    to_stop_name = to_parent_name or to_stop_name

    graph = None
    cache_path = Path(args.graph_cache) if args.graph_cache else None
    rebuild_cache = args.rebuild or args.rebuild_graph_cache

    if cache_path and cache_path.exists() and not rebuild_cache:
        try:
            with cache_path.open("rb") as handle:
                payload = pickle.load(handle)
            if isinstance(payload, dict) and payload.get("feed_id") == feed_id:
                graph = payload.get("graph")
        except Exception:
            graph = None

    if graph is None:
        cache = GraphCache(
            session=session,
            feed_id=feed_id,
            rebuild=rebuild_cache,
            symmetric_transfers=args.symmetric_transfers,
        )
        graph = cache.graph
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with cache_path.open("wb") as handle:
                pickle.dump(
                    {"feed_id": feed_id, "graph": graph},
                    handle,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )

    result = td_dijkstra(
        graph=graph,
        start_id=from_parent_id,
        goal_id=to_parent_id,
        depart_time_str=args.depart_time,
        assume_zero_missing=args.assume_zero_missing,
        transfer_penalty_sec=args.transfer_penalty,
        route_change_penalty_sec=args.route_change_penalty,
    )

    if result.arrival_time_sec is None:
        raise SystemExit(f"No path found from '{from_stop_name}' to '{to_stop_name}'.")

    route_rows = (
        session.query(Route.route_id, Route.route_short_name)
        .filter(Route.feed_id == feed_id)
        .all()
    )
    route_short_names = {
        route_id: route_short_name
        for route_id, route_short_name in route_rows
        if route_id and route_short_name
    }

    stop_name_rows = (
        session.query(Stop.stop_id, Stop.stop_name)
        .filter(Stop.feed_id == feed_id)
        .filter(Stop.stop_id.in_(result.stop_path))
        .all()
    )
    stop_names = {stop_id: stop_name for stop_id, stop_name in stop_name_rows}

    builder = ItineraryBuilder(
        stop_names=stop_names,
        route_short_names=route_short_names,
        transfer_penalty_sec=args.transfer_penalty,
    )
    itinerary = builder.build(
        result,
        from_stop_name=from_stop_name,
        to_stop_name=to_stop_name,
        depart_time_str=args.depart_time,
    )
    for line in itinerary.lines():
        print(line)


if __name__ == "__main__":
    main()
