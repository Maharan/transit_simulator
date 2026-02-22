from __future__ import annotations

from types import SimpleNamespace

from core.routing.route_planner import (
    _display_stop_ids_for_path,
    _graph_node_ids_for_stop,
)


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
