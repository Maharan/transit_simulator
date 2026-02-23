from __future__ import annotations

from types import SimpleNamespace

from core.routing.route_planner import (
    QUERY_SOURCE_NODE_PREFIX,
    QUERY_SINK_NODE_PREFIX,
    _display_stop_ids_for_path,
    _graph_node_ids_for_stop,
    _make_query_source_node_id,
    _make_query_sink_node_id,
    _strip_query_terminals_from_result,
)
from core.routing.td_dijkstra import PathResult


def test_graph_node_ids_for_stop_uses_route_stop_ids_when_available() -> None:
    graph = SimpleNamespace(
        route_stop_ids_for_stop=lambda _stop_id: {"B::trip-2", "B::trip-1"}
    )

    node_ids = _graph_node_ids_for_stop(graph, "B")
    assert node_ids == ["B::trip-1", "B::trip-2"]


def test_graph_node_ids_for_stop_falls_back_to_plain_stop_id() -> None:
    graph = SimpleNamespace()
    assert _graph_node_ids_for_stop(graph, "B") == ["B"]


def test_display_stop_ids_for_path_prefers_graph_node_metadata() -> None:
    graph = SimpleNamespace(
        nodes={
            "BT::trip-1": {"stop_id": "BT"},
            "BS::trip-1": {"stop_id": "BS"},
        }
    )
    mapping = _display_stop_ids_for_path(
        graph=graph,
        stop_ids=["BT::trip-1", "BS::trip-1"],
    )
    assert mapping == {"BT::trip-1": "BT", "BS::trip-1": "BS"}


def test_display_stop_ids_for_path_falls_back_to_trip_stop_split() -> None:
    graph = SimpleNamespace(nodes={})
    mapping = _display_stop_ids_for_path(
        graph=graph,
        stop_ids=["BT::trip-1", "S3"],
    )
    assert mapping == {"BT::trip-1": "BT", "S3": "S3"}


def test_make_query_source_node_id_uses_prefix() -> None:
    source_id = _make_query_source_node_id("AT")
    assert source_id == f"{QUERY_SOURCE_NODE_PREFIX}::AT"


def test_make_query_sink_node_id_uses_prefix() -> None:
    sink_id = _make_query_sink_node_id("BT")
    assert sink_id == f"{QUERY_SINK_NODE_PREFIX}::BT"


def test_strip_query_terminals_from_result_removes_source_and_sink_hops() -> None:
    source_id = _make_query_source_node_id("AT")
    sink_id = _make_query_sink_node_id("BT")
    result = PathResult(
        arrival_time_sec=100,
        stop_path=[source_id, "A::trip-1", "BT::trip-2", sink_id],
        edge_path=["source-edge", "edge-1", "edge-2"],
    )

    trimmed = _strip_query_terminals_from_result(
        result=result,
        query_source_node_id=source_id,
        query_sink_node_id=sink_id,
    )
    assert trimmed.arrival_time_sec == 100
    assert trimmed.stop_path == ["A::trip-1", "BT::trip-2"]
    assert trimmed.edge_path == ["edge-1"]


def test_display_stop_ids_for_path_ignores_query_terminal_nodes() -> None:
    source_id = _make_query_source_node_id("AT")
    sink_id = _make_query_sink_node_id("BT")
    graph = SimpleNamespace(nodes={})
    mapping = _display_stop_ids_for_path(
        graph=graph,
        stop_ids=[source_id, "BT::trip-1", sink_id, "S3"],
    )
    assert mapping == {"BT::trip-1": "BT", "S3": "S3"}
