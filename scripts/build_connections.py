from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from graph import GraphCache, GraphEdge, GraphNode
from gtfs.utils import resolve_feed_id
from infra import Database


def main() -> None:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(
        description="Build or rebuild cached graph nodes/edges from GTFS tables."
    )
    parser.add_argument(
        "--feed-id",
        help="GTFS feed_id to use. Required if multiple feeds exist.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild graph cache from GTFS tables.",
    )
    parser.add_argument(
        "--symmetric-transfers",
        action="store_true",
        help="Treat transfers as bidirectional edges.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        default=True,
        help="Print progress as the graph cache builds (default: on).",
    )
    parser.add_argument(
        "--no-progress",
        dest="progress",
        action="store_false",
        help="Disable progress output.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=5000,
        help="How often to print progress (default: 5000).",
    )
    parser.add_argument(
        "--ensure-indexes",
        action="store_true",
        default=True,
        help="Create helpful DB indexes if missing (default: on).",
    )
    parser.add_argument(
        "--no-indexes",
        dest="ensure_indexes",
        action="store_false",
        help="Skip creating DB indexes.",
    )
    args = parser.parse_args()

    session = Database().session()
    feed_id = resolve_feed_id(session, args.feed_id)

    GraphCache(
        session=session,
        feed_id=feed_id,
        rebuild=args.rebuild,
        symmetric_transfers=args.symmetric_transfers,
        progress=args.progress,
        progress_every=args.progress_every,
    )

    if args.ensure_indexes:
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_stops_feed_stop_id "
                "ON gtfs.stops (feed_id, stop_id)"
            )
        )
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_stops_feed_lower_name "
                "ON gtfs.stops (feed_id, lower(stop_name))"
            )
        )
        session.commit()

    node_count = (
        session.query(GraphNode.id).filter(GraphNode.feed_id == feed_id).count()
    )
    edge_count = (
        session.query(GraphEdge.id).filter(GraphEdge.feed_id == feed_id).count()
    )
    print(
        f"Graph cache ready for feed '{feed_id}': {node_count} nodes, {edge_count} edges"
    )


if __name__ == "__main__":
    main()
