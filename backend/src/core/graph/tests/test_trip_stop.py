from __future__ import annotations

import pytest

from core.graph.graph_methods.trip_stop_graph import (
    DEFAULT_TRANSFER_EDGE_PENALTY_SEC,
    TripStopEdge,
    TripStopGraph,
    build_trip_stop_graph_from_gtfs,
    make_same_stop_transfer_hub_node_id,
    make_trip_stop_node_id,
    split_trip_stop_node_id,
)
from core.graph.walk import WalkEdgeSpec
from core.routing.td_dijkstra import td_dijkstra


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


def _edge_map(graph: TripStopGraph, node_id: str) -> dict[str, TripStopEdge]:
    return {edge.to_route_stop_id: edge for edge in graph.edges_from(node_id)}


def _pattern_node_for_route(
    graph: TripStopGraph,
    *,
    stop_id: str,
    route_id: str,
) -> str:
    candidates = [
        node_id
        for node_id in graph.route_stop_ids_for_stop(stop_id)
        if graph.nodes.get(node_id, {}).get("route_id") == route_id
    ]
    if len(candidates) != 1:
        raise AssertionError(
            f"Expected exactly one node for stop={stop_id} route={route_id}, got {candidates}"
        )
    return candidates[0]


def _bucket_map(graph: TripStopGraph, node_id: str):
    return {bucket.to_stop_id: bucket for bucket in graph.trip_buckets_from(node_id)}


def test_trip_stop_node_id_round_trip() -> None:
    node_id = make_trip_stop_node_id("BT", "pattern_abc")
    assert node_id == "BT::pattern_abc"
    assert split_trip_stop_node_id(node_id) == ("BT", "pattern_abc")

    with pytest.raises(ValueError):
        split_trip_stop_node_id("invalid-node-id")


def test_trip_stop_graph_compacts_trips_to_pattern_nodes_and_sorts_departures() -> None:
    stop_time_rows = [
        ("trip-u2-a", "BT", 1, "09:00:00", "09:00:00"),
        ("trip-u2-a", "BS", 2, "09:02:00", "09:02:00"),
        ("trip-u2-b", "BT", 1, "09:05:00", "09:05:00"),
        ("trip-u2-b", "BS", 2, "09:07:00", "09:07:00"),
        ("trip-u4-a", "BT", 1, "09:01:00", "09:01:00"),
        ("trip-u4-a", "BS", 2, "09:03:00", "09:03:00"),
    ]
    session = _FakeSession(
        rows_by_query=[
            [
                ("BT", None, 53.5500, 9.9930),
                ("BS", None, 53.5600, 10.0100),
            ],
            [
                ("trip-u2-a", "U2", "svc-1", 0),
                ("trip-u2-b", "U2", "svc-1", 0),
                ("trip-u4-a", "U4", "svc-1", 0),
            ],
            [(row[0], row[1], row[2]) for row in stop_time_rows],
            stop_time_rows,
            [],
        ]
    )

    graph = build_trip_stop_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=False,
        enable_walking=False,
    )

    # Two distinct patterns: U2 and U4, each with BT/BS nodes.
    assert len(graph.nodes) == 4

    bt_u2 = _pattern_node_for_route(graph, stop_id="BT", route_id="U2")
    bs_u2 = _pattern_node_for_route(graph, stop_id="BS", route_id="U2")

    bt_u2_buckets = _bucket_map(graph, bt_u2)
    assert bs_u2 in bt_u2_buckets
    bucket = bt_u2_buckets[bs_u2]
    assert bucket.dep_secs == [9 * 3600, 9 * 3600 + 5 * 60]
    assert bucket.arr_secs == [9 * 3600 + 120, 9 * 3600 + 7 * 60]
    assert bucket.trip_ids == ["trip-u2-a", "trip-u2-b"]
    assert bucket.route_ids == ["U2", "U2"]


def test_same_stop_transfer_hub_applies_transfer_penalty_once() -> None:
    stop_time_rows = [
        ("trip-1", "A", 1, "09:00:00", "09:00:00"),
        ("trip-2", "A", 1, "09:01:00", "09:01:00"),
    ]
    session = _FakeSession(
        rows_by_query=[
            [("A", None, 53.5000, 9.9000)],
            [
                ("trip-1", "R1", "svc-1", 0),
                ("trip-2", "R2", "svc-1", 0),
            ],
            [(row[0], row[1], row[2]) for row in stop_time_rows],
            stop_time_rows,
            [],
        ]
    )

    graph = build_trip_stop_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=True,
        same_stop_transfer_sec=25,
        enable_walking=False,
    )

    a_r1 = _pattern_node_for_route(graph, stop_id="A", route_id="R1")
    a_r2 = _pattern_node_for_route(graph, stop_id="A", route_id="R2")
    a_hub = make_same_stop_transfer_hub_node_id("A")

    result = td_dijkstra(
        graph=graph,
        start_id=a_r1,
        goal_id=a_r2,
        depart_time_str="09:00:00",
        transfer_penalty_sec=300,
    )

    expected_arrival = (
        9 * 3600
        + 25
        + DEFAULT_TRANSFER_EDGE_PENALTY_SEC
        + 300
        + DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    )
    assert result.arrival_time_sec == expected_arrival
    assert result.stop_path == [a_r1, a_hub, a_r2]
    assert len(result.edge_path) == 2
    assert result.edge_path[0].weight_sec == 25 + DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    assert result.edge_path[0].apply_penalty is True
    assert result.edge_path[1].weight_sec == DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    assert result.edge_path[1].apply_penalty is False


def test_build_trip_stop_graph_routes_explicit_transfers_through_stop_hubs() -> None:
    stop_time_rows = [
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
            [
                ("trip-1", "R1", "svc-1", 0),
                ("trip-2", "R2", "svc-1", 0),
            ],
            [(row[0], row[1], row[2]) for row in stop_time_rows],
            stop_time_rows,
            [("B", "C", 90, 0)],
        ]
    )

    graph = build_trip_stop_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=False,
        symmetric_transfers=True,
        enable_walking=False,
    )

    b_r1 = _pattern_node_for_route(graph, stop_id="B", route_id="R1")
    c_r2 = _pattern_node_for_route(graph, stop_id="C", route_id="R2")
    b_hub = make_same_stop_transfer_hub_node_id("B")
    c_hub = make_same_stop_transfer_hub_node_id("C")

    b_edges = _edge_map(graph, b_r1)
    c_edges = _edge_map(graph, c_r2)
    c_hub_edges = _edge_map(graph, c_hub)
    b_hub_edges = _edge_map(graph, b_hub)

    assert c_hub in b_edges
    assert b_edges[c_hub].kind == "transfer"
    assert b_edges[c_hub].weight_sec == 90 + DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    assert b_edges[c_hub].apply_penalty is True
    assert c_r2 in c_hub_edges
    assert c_hub_edges[c_r2].weight_sec == DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    assert c_hub_edges[c_r2].apply_penalty is False

    assert b_hub in c_edges
    assert c_edges[b_hub].kind == "transfer"
    assert c_edges[b_hub].weight_sec == 90 + DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    assert c_edges[b_hub].apply_penalty is True
    assert b_r1 in b_hub_edges
    assert b_hub_edges[b_r1].weight_sec == DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    assert b_hub_edges[b_r1].apply_penalty is False

    forward_result = td_dijkstra(
        graph=graph,
        start_id=b_r1,
        goal_id=c_r2,
        depart_time_str="09:05:00",
        transfer_penalty_sec=300,
    )
    reverse_result = td_dijkstra(
        graph=graph,
        start_id=c_r2,
        goal_id=b_r1,
        depart_time_str="09:10:00",
        transfer_penalty_sec=300,
    )

    expected_extra = (90 + DEFAULT_TRANSFER_EDGE_PENALTY_SEC) + 300
    expected_hub_exit = DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    assert (
        forward_result.arrival_time_sec
        == 9 * 3600 + 5 * 60 + expected_extra + expected_hub_exit
    )
    assert forward_result.stop_path == [b_r1, c_hub, c_r2]
    assert (
        reverse_result.arrival_time_sec
        == 9 * 3600 + 10 * 60 + expected_extra + expected_hub_exit
    )
    assert reverse_result.stop_path == [c_r2, b_hub, b_r1]


def test_build_trip_stop_graph_routes_walking_transfers_through_stop_hubs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_build_walk_edges(**_kwargs):
        return [
            WalkEdgeSpec(
                from_stop_id="A",
                to_stop_id="B",
                distance_m=120,
                duration_sec=120,
            )
        ]

    monkeypatch.setattr(
        "core.graph.graph_methods.trip_stop_graph.build_walk_edges",
        _fake_build_walk_edges,
    )

    stop_time_rows = [
        ("trip-1", "A", 1, "09:00:00", "09:00:00"),
        ("trip-2", "B", 1, "09:01:00", "09:01:00"),
    ]
    session = _FakeSession(
        rows_by_query=[
            [
                ("A", None, 53.5000, 9.9000),
                ("B", None, 53.5100, 9.9100),
            ],
            [
                ("trip-1", "R1", "svc-1", 0),
                ("trip-2", "R2", "svc-1", 0),
            ],
            [(row[0], row[1], row[2]) for row in stop_time_rows],
            stop_time_rows,
            [],
        ]
    )

    graph = build_trip_stop_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=False,
        enable_walking=True,
    )

    a_r1 = _pattern_node_for_route(graph, stop_id="A", route_id="R1")
    b_r2 = _pattern_node_for_route(graph, stop_id="B", route_id="R2")
    b_hub = make_same_stop_transfer_hub_node_id("B")

    a_edges = _edge_map(graph, a_r1)
    b_hub_edges = _edge_map(graph, b_hub)

    assert b_hub in a_edges
    assert a_edges[b_hub].label == "walk"
    assert a_edges[b_hub].weight_sec == 120 + DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    assert a_edges[b_hub].apply_penalty is False
    assert b_r2 in b_hub_edges
    assert b_hub_edges[b_r2].weight_sec == DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    assert b_hub_edges[b_r2].apply_penalty is False

    result = td_dijkstra(
        graph=graph,
        start_id=a_r1,
        goal_id=b_r2,
        depart_time_str="09:00:00",
        transfer_penalty_sec=300,
    )

    assert (
        result.arrival_time_sec
        == 9 * 3600 + 120 + 2 * DEFAULT_TRANSFER_EDGE_PENALTY_SEC
    )
    assert result.stop_path == [a_r1, b_hub, b_r2]


def test_trip_stop_graph_ride_buckets_are_compatible_with_td_dijkstra() -> None:
    stop_time_rows = [
        ("trip-1", "A", 1, "09:00:00", "09:00:00"),
        ("trip-1", "B", 2, "09:02:00", "09:02:00"),
        ("trip-2", "A", 1, "09:05:00", "09:05:00"),
        ("trip-2", "B", 2, "09:07:00", "09:07:00"),
    ]
    session = _FakeSession(
        rows_by_query=[
            [
                ("A", None, 53.5000, 9.9000),
                ("B", None, 53.5100, 9.9100),
            ],
            [
                ("trip-1", "R1", "svc-1", 0),
                ("trip-2", "R1", "svc-1", 0),
            ],
            [(row[0], row[1], row[2]) for row in stop_time_rows],
            stop_time_rows,
            [],
        ]
    )

    graph = build_trip_stop_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=False,
        enable_walking=False,
    )

    a_r1 = _pattern_node_for_route(graph, stop_id="A", route_id="R1")
    b_r1 = _pattern_node_for_route(graph, stop_id="B", route_id="R1")

    early_result = td_dijkstra(
        graph=graph,
        start_id=a_r1,
        goal_id=b_r1,
        depart_time_str="08:59:00",
    )
    later_result = td_dijkstra(
        graph=graph,
        start_id=a_r1,
        goal_id=b_r1,
        depart_time_str="09:03:00",
    )

    assert early_result.arrival_time_sec == 9 * 3600 + 120
    assert later_result.arrival_time_sec == 9 * 3600 + 7 * 60
    assert early_result.stop_path == [a_r1, b_r1]
    assert later_result.stop_path == [a_r1, b_r1]


def test_build_trip_stop_graph_logs_progress_for_transfer_and_walk_edges(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _fake_build_walk_edges(**_kwargs):
        return [
            WalkEdgeSpec(
                from_stop_id="A",
                to_stop_id="B",
                distance_m=100,
                duration_sec=120,
            )
        ]

    monkeypatch.setattr(
        "core.graph.graph_methods.trip_stop_graph.build_walk_edges",
        _fake_build_walk_edges,
    )

    stop_time_rows = [
        ("trip-1", "A", 1, "09:00:00", "09:00:00"),
        ("trip-1", "B", 2, "09:02:00", "09:02:00"),
        ("trip-2", "A", 1, "09:01:00", "09:01:00"),
        ("trip-2", "B", 2, "09:03:00", "09:03:00"),
    ]
    session = _FakeSession(
        rows_by_query=[
            [
                ("A", None, 53.5000, 9.9000),
                ("B", None, 53.5100, 9.9100),
            ],
            [
                ("trip-1", "R1", "svc-1", 0),
                ("trip-2", "R2", "svc-1", 0),
            ],
            [(row[0], row[1], row[2]) for row in stop_time_rows],
            stop_time_rows,
            [("A", "B", 90, 0)],
        ]
    )

    build_trip_stop_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=True,
        symmetric_transfers=False,
        enable_walking=True,
        progress=True,
        progress_every=1,
    )

    output = capsys.readouterr().out
    assert "same-stop transfer edges so far" in output
    assert "inter-stop transfer edges so far" in output
    assert "walking edges so far in trip-stop graph" in output
