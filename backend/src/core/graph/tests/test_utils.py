from __future__ import annotations

from unittest.mock import Mock

from core.graph.utils import resolve_parent_stop


def _query_mock(return_value):
    query = Mock()
    query.filter.return_value = query
    query.first.return_value = return_value
    return query


def test_resolve_parent_stop_returns_parent_stop_name_when_available() -> None:
    session = Mock()
    session.query.side_effect = [
        _query_mock(("child-stop", "parent-stop")),
        _query_mock(("Parent Station",)),
    ]

    parent_id, parent_name = resolve_parent_stop(session, "feed-1", "child-stop")

    assert parent_id == "parent-stop"
    assert parent_name == "Parent Station"


def test_resolve_parent_stop_returns_original_stop_when_no_parent() -> None:
    session = Mock()
    session.query.side_effect = [_query_mock(("stop-1", None))]

    parent_id, parent_name = resolve_parent_stop(session, "feed-1", "stop-1")

    assert parent_id == "stop-1"
    assert parent_name is None
