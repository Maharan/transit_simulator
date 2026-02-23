from __future__ import annotations

import pytest

from core.graph.graph_methods.trip_stop_graph import (
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


def test_trip_stop_node_id_round_trip() -> None:
    node_id = make_trip_stop_node_id("BT", "trip-u2")
    assert node_id == "BT::trip-u2"
    assert split_trip_stop_node_id(node_id) == ("BT", "trip-u2")

    with pytest.raises(ValueError):
        split_trip_stop_node_id("invalid-node-id")


def test_trip_stop_graph_keeps_single_preferred_edge_per_direction() -> None:
    graph = TripStopGraph()
    from_id = make_trip_stop_node_id("A", "trip-1")
    to_id = make_trip_stop_node_id("B", "trip-2")

    graph.add_edge(
        from_id,
        TripStopEdge(
            to_route_stop_id=to_id,
            weight_sec=30,
            kind="transfer",
            apply_penalty=False,
            label="walk",
        ),
    )
    graph.add_edge(
        from_id,
        TripStopEdge(
            to_route_stop_id=to_id,
            weight_sec=60,
            kind="transfer",
            transfer_type=2,
        ),
    )
    graph.add_edge(
        from_id,
        TripStopEdge(
            to_route_stop_id=to_id,
            weight_sec=120,
            kind="ride",
            trip_id="trip-1",
            route_id="route-1",
            dep_time_sec=9 * 3600,
            arr_time_sec=9 * 3600 + 120,
        ),
    )

    edges = graph.edges_from(from_id)
    assert len(edges) == 1
    edge = edges[0]
    assert edge.kind == "ride"
    assert edge.weight_sec == 120


def test_build_trip_stop_graph_creates_stop_trip_nodes_and_same_stop_transfer_hubs() -> (
    None
):
    session = _FakeSession(
        rows_by_query=[
            [
                ("BT", None, 53.5500, 9.9930),
                ("BS", None, 53.5600, 10.0100),
            ],
            [
                ("trip-u2", "U2", "svc-1"),
                ("trip-u4", "U4", "svc-1"),
            ],
            [
                ("trip-u2", "BT", 1, "09:00:00", "09:00:00"),
                ("trip-u2", "BS", 2, "09:02:00", "09:02:00"),
                ("trip-u4", "BT", 1, "09:01:00", "09:01:00"),
                ("trip-u4", "BS", 2, "09:03:00", "09:03:00"),
            ],
            [],
        ]
    )

    graph = build_trip_stop_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=True,
        enable_walking=False,
    )

    bt_u2 = make_trip_stop_node_id("BT", "trip-u2")
    bt_u4 = make_trip_stop_node_id("BT", "trip-u4")
    bs_u2 = make_trip_stop_node_id("BS", "trip-u2")
    bs_u4 = make_trip_stop_node_id("BS", "trip-u4")
    bt_hub = make_same_stop_transfer_hub_node_id("BT")
    bs_hub = make_same_stop_transfer_hub_node_id("BS")

    assert set(graph.nodes) == {bt_u2, bt_u4, bs_u2, bs_u4, bt_hub, bs_hub}

    bt_u2_edges = _edge_map(graph, bt_u2)
    bt_u4_edges = _edge_map(graph, bt_u4)
    bs_u2_edges = _edge_map(graph, bs_u2)
    bs_u4_edges = _edge_map(graph, bs_u4)
    bt_hub_edges = _edge_map(graph, bt_hub)
    bs_hub_edges = _edge_map(graph, bs_hub)

    assert set(bt_u2_edges) == {bs_u2, bt_hub}
    assert set(bt_u4_edges) == {bs_u4, bt_hub}
    assert set(bs_u2_edges) == {bs_hub}
    assert set(bs_u4_edges) == {bs_hub}
    assert set(bt_hub_edges) == {bt_u2, bt_u4}
    assert set(bs_hub_edges) == {bs_u2, bs_u4}

    assert bt_u2_edges[bs_u2].kind == "ride"
    assert bt_u2_edges[bt_hub].kind == "transfer"
    assert bt_u2_edges[bt_hub].weight_sec == 0
    assert bt_u2_edges[bt_hub].apply_penalty is True
    assert bt_hub_edges[bt_u4].kind == "transfer"
    assert bt_hub_edges[bt_u4].apply_penalty is False


def test_same_stop_transfer_hub_applies_transfer_penalty_once() -> None:
    session = _FakeSession(
        rows_by_query=[
            [
                ("A", None, 53.5000, 9.9000),
            ],
            [
                ("trip-1", "R1", "svc-1"),
                ("trip-2", "R2", "svc-1"),
            ],
            [
                ("trip-1", "A", 1, "09:00:00", "09:00:00"),
                ("trip-2", "A", 1, "09:01:00", "09:01:00"),
            ],
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

    a_trip_1 = make_trip_stop_node_id("A", "trip-1")
    a_trip_2 = make_trip_stop_node_id("A", "trip-2")
    a_hub = make_same_stop_transfer_hub_node_id("A")

    result = td_dijkstra(
        graph=graph,
        start_id=a_trip_1,
        goal_id=a_trip_2,
        depart_time_str="09:00:00",
        transfer_penalty_sec=300,
    )

    assert result.arrival_time_sec == 9 * 3600 + 25 + 300
    assert result.stop_path == [a_trip_1, a_hub, a_trip_2]
    assert len(result.edge_path) == 2
    assert result.edge_path[0].apply_penalty is True
    assert result.edge_path[1].apply_penalty is False


def test_build_trip_stop_graph_routes_explicit_transfers_through_stop_hubs() -> None:
    session = _FakeSession(
        rows_by_query=[
            [
                ("A", None, 53.5000, 9.9000),
                ("B", None, 53.5100, 9.9100),
                ("C", None, 53.5200, 9.9200),
            ],
            [
                ("trip-1", "R1", "svc-1"),
                ("trip-2", "R2", "svc-1"),
            ],
            [
                ("trip-1", "A", 1, "09:00:00", "09:00:00"),
                ("trip-1", "B", 2, "09:05:00", "09:05:00"),
                ("trip-2", "C", 1, "09:10:00", "09:10:00"),
            ],
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

    b_trip_1 = make_trip_stop_node_id("B", "trip-1")
    c_trip_2 = make_trip_stop_node_id("C", "trip-2")
    b_hub = make_same_stop_transfer_hub_node_id("B")
    c_hub = make_same_stop_transfer_hub_node_id("C")

    b_edges = _edge_map(graph, b_trip_1)
    c_edges = _edge_map(graph, c_trip_2)
    c_hub_edges = _edge_map(graph, c_hub)
    b_hub_edges = _edge_map(graph, b_hub)

    assert c_hub in b_edges
    assert b_edges[c_hub].kind == "transfer"
    assert b_edges[c_hub].weight_sec == 90
    assert b_edges[c_hub].apply_penalty is True
    assert c_trip_2 in c_hub_edges
    assert c_hub_edges[c_trip_2].weight_sec == 0
    assert c_hub_edges[c_trip_2].apply_penalty is False

    assert b_hub in c_edges
    assert c_edges[b_hub].kind == "transfer"
    assert c_edges[b_hub].weight_sec == 90
    assert c_edges[b_hub].apply_penalty is True
    assert b_trip_1 in b_hub_edges
    assert b_hub_edges[b_trip_1].weight_sec == 0
    assert b_hub_edges[b_trip_1].apply_penalty is False

    forward_result = td_dijkstra(
        graph=graph,
        start_id=b_trip_1,
        goal_id=c_trip_2,
        depart_time_str="09:05:00",
        transfer_penalty_sec=300,
    )
    reverse_result = td_dijkstra(
        graph=graph,
        start_id=c_trip_2,
        goal_id=b_trip_1,
        depart_time_str="09:10:00",
        transfer_penalty_sec=300,
    )

    assert forward_result.arrival_time_sec == 9 * 3600 + 5 * 60 + 90 + 300
    assert forward_result.stop_path == [b_trip_1, c_hub, c_trip_2]
    assert reverse_result.arrival_time_sec == 9 * 3600 + 10 * 60 + 90 + 300
    assert reverse_result.stop_path == [c_trip_2, b_hub, b_trip_1]


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

    session = _FakeSession(
        rows_by_query=[
            [
                ("A", None, 53.5000, 9.9000),
                ("B", None, 53.5100, 9.9100),
            ],
            [
                ("trip-1", "R1", "svc-1"),
                ("trip-2", "R2", "svc-1"),
            ],
            [
                ("trip-1", "A", 1, "09:00:00", "09:00:00"),
                ("trip-2", "B", 1, "09:01:00", "09:01:00"),
            ],
            [],
        ]
    )

    graph = build_trip_stop_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=False,
        enable_walking=True,
    )

    a_trip_1 = make_trip_stop_node_id("A", "trip-1")
    b_trip_2 = make_trip_stop_node_id("B", "trip-2")
    b_hub = make_same_stop_transfer_hub_node_id("B")

    a_edges = _edge_map(graph, a_trip_1)
    b_hub_edges = _edge_map(graph, b_hub)

    assert b_hub in a_edges
    assert a_edges[b_hub].label == "walk"
    assert a_edges[b_hub].weight_sec == 120
    assert a_edges[b_hub].apply_penalty is False
    assert b_trip_2 in b_hub_edges
    assert b_hub_edges[b_trip_2].weight_sec == 0
    assert b_hub_edges[b_trip_2].apply_penalty is False

    result = td_dijkstra(
        graph=graph,
        start_id=a_trip_1,
        goal_id=b_trip_2,
        depart_time_str="09:00:00",
        transfer_penalty_sec=300,
    )

    assert result.arrival_time_sec == 9 * 3600 + 120
    assert result.stop_path == [a_trip_1, b_hub, b_trip_2]


def test_trip_stop_graph_ride_edges_are_compatible_with_td_dijkstra() -> None:
    session = _FakeSession(
        rows_by_query=[
            [
                ("A", None, 53.5000, 9.9000),
                ("B", None, 53.5100, 9.9100),
            ],
            [
                ("trip-1", "R1", "svc-1"),
            ],
            [
                ("trip-1", "A", 1, "09:00:00", "09:00:00"),
                ("trip-1", "B", 2, "09:02:00", "09:02:00"),
            ],
            [],
        ]
    )

    graph = build_trip_stop_graph_from_gtfs(
        session=session,
        feed_id="feed-1",
        connect_same_stop_transfers=False,
        enable_walking=False,
    )

    a_trip_1 = make_trip_stop_node_id("A", "trip-1")
    b_trip_1 = make_trip_stop_node_id("B", "trip-1")
    result = td_dijkstra(
        graph=graph,
        start_id=a_trip_1,
        goal_id=b_trip_1,
        depart_time_str="08:59:00",
    )

    assert result.arrival_time_sec == 9 * 3600 + 120
    assert result.stop_path == [a_trip_1, b_trip_1]
    assert result.edge_path[0].kind == "ride"


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

    session = _FakeSession(
        rows_by_query=[
            [
                ("A", None, 53.5000, 9.9000),
                ("B", None, 53.5100, 9.9100),
            ],
            [
                ("trip-1", "R1", "svc-1"),
                ("trip-2", "R2", "svc-1"),
            ],
            [
                ("trip-1", "A", 1, "09:00:00", "09:00:00"),
                ("trip-1", "B", 2, "09:02:00", "09:02:00"),
                ("trip-2", "A", 1, "09:01:00", "09:01:00"),
                ("trip-2", "B", 2, "09:03:00", "09:03:00"),
            ],
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
