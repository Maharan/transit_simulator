from __future__ import annotations


import core.graph.graph_methods.multi_edge_graph as build_module
from core.graph.graph_methods.multi_edge_graph import Edge, Graph
from core.graph.walk import WalkEdgeSpec


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def yield_per(self, _size):
        return iter(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *_args):
        return _FakeQuery(self._rows)


def test_time_to_seconds_parses_and_rejects_invalid_values() -> None:
    assert build_module._time_to_seconds("08:30:05") == 30605
    assert build_module._time_to_seconds("24:05:00") == 86700
    assert build_module._time_to_seconds("08:99:00") is None
    assert build_module._time_to_seconds("bad") is None
    assert build_module._time_to_seconds(None) is None


def test_edge_timing_accepts_non_negative_durations() -> None:
    weight_sec, dep_sec, arr_sec = build_module._edge_timing("10:00:00", "10:05:00")
    assert weight_sec == 300
    assert dep_sec == 36000
    assert arr_sec == 36300

    weight_sec, dep_sec, arr_sec = build_module._edge_timing("10:05:00", "10:00:00")
    assert weight_sec is None
    assert dep_sec == 36300
    assert arr_sec == 36000


def test_graph_indexes_transfer_edges_separately() -> None:
    graph = Graph()
    graph.add_node("A", 53.5, 9.9)
    graph.add_node("B", 53.6, 9.8)
    graph.add_edge("A", Edge(to_stop_id="B", weight_sec=120, kind="transfer"))
    graph.add_edge("A", Edge(to_stop_id="B", weight_sec=240, kind="trip"))

    assert len(graph.edges_from("A")) == 2
    assert len(graph.transfer_edges_from("A")) == 1


def test_add_walk_edges_marks_them_penalty_free(monkeypatch) -> None:
    graph = Graph()
    graph.add_edge("A", Edge(to_stop_id="X", weight_sec=30, kind="transfer"))

    def fake_build_walk_edges(**kwargs):
        assert ("A", "X") in kwargs["existing_edges"]
        return [WalkEdgeSpec("A", "B", distance_m=100, duration_sec=75)]

    monkeypatch.setattr(build_module, "build_walk_edges", fake_build_walk_edges)

    added_count = build_module._add_walk_edges(
        graph=graph,
        stop_coords={"A": (53.55, 9.99), "B": (53.551, 9.99)},
        walk_max_distance_m=300,
        walk_speed_mps=1.4,
        walk_max_neighbors=6,
    )

    assert added_count == 1
    edge = graph.transfer_edges_from("A")[-1]
    assert edge.label == "walk"
    assert edge.apply_penalty is False
    assert edge.weight_sec == 75


def test_load_parent_stop_coords_maps_parent_and_filters_known_nodes() -> None:
    session = _FakeSession(
        rows=[
            ("child-1", "parent-1", 53.0, 9.0),
            ("child-2", "parent-2", 53.1, 9.1),
            ("stop-a", None, 53.2, 9.2),
            ("stop-b", None, None, 9.2),
            (None, None, 53.3, 9.3),
        ]
    )
    coords = build_module._load_parent_stop_coords(
        session=session,
        feed_id="feed-1",
        known_nodes={"parent-1", "stop-a"},
    )
    assert coords == {
        "parent-1": (53.0, 9.0),
        "stop-a": (53.2, 9.2),
    }
