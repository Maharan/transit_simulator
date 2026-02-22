from __future__ import annotations

from core.graph.graph_methods.trip_stop_anytime_graph import (
    TripStopAnytimeEdge,
    TripStopAnytimeGraph,
    build_trip_stop_anytime_graph_from_gtfs,
)
from core.graph.graph_methods.trip_stop_graph import make_trip_stop_node_id


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def yield_per(self, _size):
        return iter(self._rows)


class _FakeSession:
    def __init__(self, rows_by_query):
        self._rows_by_query = rows_by_query
        self._query_index = 0

    def query(self, *_args):
        if self._query_index >= len(self._rows_by_query):
            raise AssertionError("Unexpected query call in test fake session.")
        rows = self._rows_by_query[self._query_index]
        self._query_index += 1
        return _FakeQuery(rows)


def _edge_map(
    graph: TripStopAnytimeGraph,
    node_id: str,
) -> dict[str, TripStopAnytimeEdge]:
    return {edge.to_route_stop_id: edge for edge in graph.edges_from(node_id)}


def test_anytime_graph_ride_edges_store_weight_and_headway_without_schedule_fields() -> (
    None
):
    stop_times = [
        ("trip-1", "BT", 1, "09:00:00", "09:00:00"),
        ("trip-1", "BS", 2, "09:02:00", "09:02:00"),
        ("trip-2", "BT", 1, "09:10:00", "09:10:00"),
        ("trip-2", "BS", 2, "09:13:00", "09:13:00"),
    ]
    session = _FakeSession(
        rows_by_query=[
            [("BT", None, 53.5500, 9.9930), ("BS", None, 53.5600, 10.0100)],
            [("trip-1", "19", "svc-1", 0), ("trip-2", "19", "svc-1", 0)],
            stop_times,
            stop_times,
            [],
        ]
    )

    graph = build_trip_stop_anytime_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=False,
        enable_walking=False,
    )
    bt_trip_1 = make_trip_stop_node_id("BT", "trip-1")
    bs_trip_1 = make_trip_stop_node_id("BS", "trip-1")
    edge = _edge_map(graph, bt_trip_1)[bs_trip_1]

    assert edge.kind == "ride"
    assert edge.weight_sec == 150
    assert edge.headway_sec == 600
    assert not hasattr(edge, "dep_time")
    assert not hasattr(edge, "arr_time")
    assert graph.route_headways[("19", "svc-1", 0)] == 600


def test_anytime_graph_builds_same_stop_transfers_between_trip_variants() -> None:
    stop_times = [
        ("trip-u2", "BT", 1, "09:00:00", "09:00:00"),
        ("trip-u2", "BS", 2, "09:02:00", "09:02:00"),
        ("trip-u4", "BT", 1, "09:10:00", "09:10:00"),
        ("trip-u4", "BS", 2, "09:12:00", "09:12:00"),
    ]
    session = _FakeSession(
        rows_by_query=[
            [("BT", None, 53.5500, 9.9930), ("BS", None, 53.5600, 10.0100)],
            [("trip-u2", "U2", "svc-1", 0), ("trip-u4", "U4", "svc-1", 0)],
            stop_times,
            stop_times,
            [],
        ]
    )

    graph = build_trip_stop_anytime_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=True,
        same_stop_transfer_sec=45,
        enable_walking=False,
    )

    bt_u2 = make_trip_stop_node_id("BT", "trip-u2")
    bt_u4 = make_trip_stop_node_id("BT", "trip-u4")
    bs_u2 = make_trip_stop_node_id("BS", "trip-u2")
    edge_map = _edge_map(graph, bt_u2)

    assert bs_u2 in edge_map
    assert bt_u4 in edge_map
    assert edge_map[bt_u4].kind == "transfer"
    assert edge_map[bt_u4].weight_sec == 45


def test_anytime_graph_uses_default_headway_when_no_route_headway_can_be_inferred() -> (
    None
):
    stop_times = [
        ("trip-1", "A", 1, "09:00:00", "09:00:00"),
        ("trip-1", "B", 2, "09:05:00", "09:05:00"),
    ]
    session = _FakeSession(
        rows_by_query=[
            [("A", None, 53.5000, 9.9000), ("B", None, 53.5100, 9.9100)],
            [("trip-1", "R1", "svc-1", 1)],
            stop_times,
            stop_times,
            [],
        ]
    )

    graph = build_trip_stop_anytime_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=False,
        default_headway_sec=900,
        enable_walking=False,
    )

    a_trip_1 = make_trip_stop_node_id("A", "trip-1")
    b_trip_1 = make_trip_stop_node_id("B", "trip-1")
    edge = _edge_map(graph, a_trip_1)[b_trip_1]
    assert edge.kind == "ride"
    assert edge.headway_sec == 900


def test_anytime_graph_expands_explicit_transfers_across_trip_stop_nodes() -> None:
    stop_times = [
        ("trip-1", "A", 1, "09:00:00", "09:00:00"),
        ("trip-1", "B", 2, "09:05:00", "09:05:00"),
        ("trip-2", "C", 1, "09:10:00", "09:10:00"),
    ]
    session = _FakeSession(
        rows_by_query=[
            [
                ("A", None, 53.5000, 9.9000),
                ("B", None, 53.5100, 9.9100),
                ("C", None, 53.5200, 9.9200),
            ],
            [("trip-1", "R1", "svc-1", 0), ("trip-2", "R2", "svc-1", 1)],
            stop_times,
            stop_times,
            [("B", "C", 90, 0)],
        ]
    )

    graph = build_trip_stop_anytime_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=False,
        symmetric_transfers=True,
        enable_walking=False,
    )

    b_trip_1 = make_trip_stop_node_id("B", "trip-1")
    c_trip_2 = make_trip_stop_node_id("C", "trip-2")
    b_edges = _edge_map(graph, b_trip_1)
    c_edges = _edge_map(graph, c_trip_2)

    assert c_trip_2 in b_edges
    assert b_edges[c_trip_2].kind == "transfer"
    assert b_edges[c_trip_2].weight_sec == 90
    assert b_trip_1 in c_edges
    assert c_edges[b_trip_1].kind == "transfer"
    assert c_edges[b_trip_1].weight_sec == 90
