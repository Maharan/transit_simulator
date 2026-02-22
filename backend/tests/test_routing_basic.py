from __future__ import annotations

from dataclasses import dataclass

from core.routing.td_dijkstra import td_dijkstra


@dataclass(frozen=True)
class _Edge:
    to_stop_id: str
    weight_sec: int | None
    kind: str
    route_id: str | None = None
    trip_id: str | None = None
    dep_time: str | None = None
    arr_time: str | None = None
    dep_time_sec: int | None = None
    arr_time_sec: int | None = None
    transfer_type: int | None = None
    apply_penalty: bool = True
    label: str | None = None


class _Graph:
    def __init__(self, adjacency: dict[str, list[_Edge]]) -> None:
        self._adjacency = adjacency

    def edges_from(self, stop_id: str):
        return self._adjacency.get(stop_id, [])

    def transfer_edges_from(self, stop_id: str):
        return [
            edge for edge in self._adjacency.get(stop_id, []) if edge.kind == "transfer"
        ]

    def trip_buckets_from(self, _stop_id: str):
        return []


def test_td_dijkstra_applies_transfer_penalty() -> None:
    graph = _Graph(
        {
            "A": [_Edge(to_stop_id="B", weight_sec=60, kind="transfer")],
            "B": [],
        }
    )

    result = td_dijkstra(
        graph=graph,
        start_id="A",
        goal_id="B",
        depart_time_str="09:00:00",
        transfer_penalty_sec=300,
    )
    assert result.arrival_time_sec == 9 * 3600 + 360
    assert result.stop_path == ["A", "B"]


def test_td_dijkstra_returns_no_path_when_unreachable() -> None:
    graph = _Graph({"A": [], "B": []})
    result = td_dijkstra(
        graph=graph,
        start_id="A",
        goal_id="B",
        depart_time_str="09:00:00",
    )
    assert result.arrival_time_sec is None
    assert result.stop_path == []
    assert result.edge_path == []
