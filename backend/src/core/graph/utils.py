from __future__ import annotations

from core.gtfs.models import Stop


def resolve_parent_stop(session, feed_id: str, stop_id: str) -> tuple[str, str | None]:
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
