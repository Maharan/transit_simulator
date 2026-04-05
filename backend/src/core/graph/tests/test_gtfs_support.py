from __future__ import annotations

from core.graph.graph_methods.gtfs_support import (
    edge_timing,
    load_parent_stop_coords,
    load_stop_context,
    load_trip_metadata,
    time_to_seconds,
)


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def yield_per(self, _size):
        return iter(self._rows)


class _FakeSession:
    def __init__(self, rows_by_query):
        self._rows_by_query = rows_by_query
        self._query_index = 0

    def query(self, *_args):
        rows = self._rows_by_query[self._query_index]
        self._query_index += 1
        return _FakeQuery(rows)


def test_time_to_seconds_and_edge_timing_handle_valid_and_invalid_inputs() -> None:
    assert time_to_seconds("08:30:05") == 30605
    assert time_to_seconds("bad") is None
    assert time_to_seconds(None) is None

    weight_sec, dep_sec, arr_sec = edge_timing("10:00:00", "10:05:00")
    assert weight_sec == 300
    assert dep_sec == 36000
    assert arr_sec == 36300

    weight_sec, dep_sec, arr_sec = edge_timing("10:05:00", "10:00:00")
    assert weight_sec is None
    assert dep_sec == 36300
    assert arr_sec == 36000


def test_load_stop_context_normalizes_parent_stops_and_tracks_stop_count() -> None:
    session = _FakeSession(
        rows_by_query=[
            [
                ("child-1", "parent-1", 53.0, 9.0),
                ("child-2", "parent-1", 53.1, 9.1),
                ("stop-a", None, 53.2, 9.2),
                (None, None, 53.3, 9.3),
            ]
        ]
    )

    context = load_stop_context(session, "feed-1")

    assert context.stop_count == 3
    assert context.canonical_stop_by_stop_id == {
        "child-1": "parent-1",
        "child-2": "parent-1",
        "stop-a": "stop-a",
    }
    assert context.coordinates_by_canonical_stop_id == {
        "parent-1": (53.0, 9.0),
        "stop-a": (53.2, 9.2),
    }


def test_load_parent_stop_coords_can_filter_to_known_nodes() -> None:
    session = _FakeSession(
        rows_by_query=[
            [
                ("child-1", "parent-1", 53.0, 9.0),
                ("child-2", "parent-2", 53.1, 9.1),
                ("stop-a", None, 53.2, 9.2),
            ]
        ]
    )

    coords = load_parent_stop_coords(
        session,
        "feed-1",
        known_nodes={"parent-1", "stop-a"},
    )

    assert coords == {
        "parent-1": (53.0, 9.0),
        "stop-a": (53.2, 9.2),
    }


def test_load_trip_metadata_preserves_route_service_and_direction() -> None:
    session = _FakeSession(
        rows_by_query=[
            [
                ("trip-1", "route-1", "svc-1", 0),
                ("trip-2", "route-2", "svc-2", 1),
                (None, "route-3", "svc-3", 0),
            ]
        ]
    )

    trip_meta = load_trip_metadata(session, "feed-1")

    assert trip_meta["trip-1"].route_id == "route-1"
    assert trip_meta["trip-1"].service_id == "svc-1"
    assert trip_meta["trip-1"].direction_id == 0
    assert trip_meta["trip-2"].direction_id == 1
    assert None not in trip_meta
