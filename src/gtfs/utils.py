from __future__ import annotations

from sqlalchemy import func

from gtfs.models import Stop


def resolve_feed_id(session, requested_feed_id: str | None) -> str:
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


def resolve_stop_by_name(session, feed_id: str, name: str) -> tuple[str, str]:
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
