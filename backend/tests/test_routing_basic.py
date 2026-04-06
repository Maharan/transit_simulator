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


class _OverrideEdgeModeGraph(_Graph):
    _use_bucket_mode = False

    def transfer_edges_from(self, _stop_id: str):
        return []

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


def test_td_dijkstra_debug_progress_prints(capsys) -> None:
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
        debug_progress=True,
        debug_progress_every=1,
    )

    assert result.arrival_time_sec == 9 * 3600 + 60
    output = capsys.readouterr().out
    assert "Dijkstra progress: searching A -> B from 09:00:00." in output
    assert "Dijkstra progress: expanded 1 state(s)" in output
    assert "Dijkstra progress: done after expanding" in output


def test_td_dijkstra_respects_explicit_edge_mode_override() -> None:
    graph = _OverrideEdgeModeGraph(
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


def test_td_dijkstra_does_not_board_scheduled_trip_in_the_past() -> None:
    graph = _OverrideEdgeModeGraph(
        {
            "A": [
                _Edge(
                    to_stop_id="B",
                    weight_sec=120,
                    kind="ride",
                    route_id="U1",
                    trip_id="trip-1",
                    dep_time_sec=8 * 3600,
                    arr_time_sec=8 * 3600 + 120,
                )
            ],
            "B": [],
        }
    )

    result = td_dijkstra(
        graph=graph,
        start_id="A",
        goal_id="B",
        depart_time_str="09:00:00",
    )
    assert result.arrival_time_sec is None
    assert result.stop_path == []
    assert result.edge_path == []


def test_td_dijkstra_uses_weight_for_unscheduled_ride_edges() -> None:
    graph = _OverrideEdgeModeGraph(
        {
            "A": [
                _Edge(
                    to_stop_id="B",
                    weight_sec=120,
                    kind="ride",
                    route_id="U1",
                    trip_id="trip-1",
                )
            ],
            "B": [],
        }
    )

    result = td_dijkstra(
        graph=graph,
        start_id="A",
        goal_id="B",
        depart_time_str="09:00:00",
    )
    assert result.arrival_time_sec == 9 * 3600 + 120
    assert result.stop_path == ["A", "B"]


def test_td_dijkstra_respects_max_wait_for_scheduled_ride() -> None:
    graph = _OverrideEdgeModeGraph(
        {
            "A": [
                _Edge(
                    to_stop_id="B",
                    weight_sec=120,
                    kind="ride",
                    route_id="U1",
                    trip_id="trip-1",
                    dep_time_sec=9 * 3600 + 1800,
                    arr_time_sec=9 * 3600 + 1920,
                )
            ],
            "B": [],
        }
    )

    result_blocked = td_dijkstra(
        graph=graph,
        start_id="A",
        goal_id="B",
        depart_time_str="09:00:00",
        max_wait_sec=1200,
    )
    assert result_blocked.arrival_time_sec is None

    result_allowed = td_dijkstra(
        graph=graph,
        start_id="A",
        goal_id="B",
        depart_time_str="09:00:00",
        max_wait_sec=1800,
    )
    assert result_allowed.arrival_time_sec == 9 * 3600 + 1920


def test_td_dijkstra_keeps_first_departure_per_route_when_state_by_route() -> None:
    graph = _OverrideEdgeModeGraph(
        {
            "A": [
                _Edge(
                    to_stop_id="B",
                    weight_sec=60,
                    kind="ride",
                    route_id="R1",
                    trip_id="trip-later",
                    dep_time_sec=9 * 3600 + 300,
                    arr_time_sec=9 * 3600 + 360,
                ),
                _Edge(
                    to_stop_id="B",
                    weight_sec=60,
                    kind="ride",
                    route_id="R1",
                    trip_id="trip-earlier",
                    dep_time_sec=9 * 3600 + 120,
                    arr_time_sec=9 * 3600 + 180,
                ),
            ],
            "B": [],
        }
    )

    result = td_dijkstra(
        graph=graph,
        start_id="A",
        goal_id="B",
        depart_time_str="09:00:00",
        state_by="route",
    )
    assert result.arrival_time_sec == 9 * 3600 + 180
    assert result.stop_path == ["A", "B"]


def test_td_dijkstra_keeps_first_departure_per_trip_when_state_by_trip() -> None:
    graph = _OverrideEdgeModeGraph(
        {
            "A": [
                _Edge(
                    to_stop_id="B",
                    weight_sec=60,
                    kind="ride",
                    route_id="R1",
                    trip_id="trip-a",
                    dep_time_sec=9 * 3600 + 300,
                    arr_time_sec=9 * 3600 + 360,
                ),
                _Edge(
                    to_stop_id="B",
                    weight_sec=60,
                    kind="ride",
                    route_id="R1",
                    trip_id="trip-b",
                    dep_time_sec=9 * 3600 + 120,
                    arr_time_sec=9 * 3600 + 180,
                ),
            ],
            "B": [],
        }
    )

    result = td_dijkstra(
        graph=graph,
        start_id="A",
        goal_id="B",
        depart_time_str="09:00:00",
        state_by="trip",
    )
    assert result.arrival_time_sec == 9 * 3600 + 180
    assert result.stop_path == ["A", "B"]


def test_td_dijkstra_haversine_heuristic_keeps_optimal_path() -> None:
    graph = _OverrideEdgeModeGraph(
        {
            "A": [
                _Edge(to_stop_id="B", weight_sec=60, kind="transfer"),
                _Edge(to_stop_id="C", weight_sec=10, kind="transfer"),
            ],
            "B": [],
            "C": [_Edge(to_stop_id="B", weight_sec=300, kind="transfer")],
        }
    )
    graph.nodes = {
        "A": {"stop_lat": 53.550, "stop_lon": 9.993},
        "B": {"stop_lat": 53.560, "stop_lon": 10.003},
        "C": {"stop_lat": 53.900, "stop_lon": 10.900},
    }

    result = td_dijkstra(
        graph=graph,
        start_id="A",
        goal_id="B",
        depart_time_str="09:00:00",
        transfer_penalty_sec=0,
        heuristic_max_speed_mps=55.0,
    )
    assert result.arrival_time_sec == 9 * 3600 + 60
    assert result.stop_path == ["A", "B"]


def test_td_dijkstra_does_not_treat_transfer_penalty_as_route_change_penalty() -> None:
    graph = _OverrideEdgeModeGraph(
        {
            "A": [
                _Edge(
                    to_stop_id="B",
                    weight_sec=60,
                    kind="ride",
                    route_id="R1",
                    trip_id="trip-1",
                    dep_time_sec=9 * 3600,
                    arr_time_sec=9 * 3600 + 60,
                )
            ],
            "B": [
                _Edge(
                    to_stop_id="C",
                    weight_sec=60,
                    kind="ride",
                    route_id="R2",
                    trip_id="trip-2",
                    dep_time_sec=9 * 3600 + 60,
                    arr_time_sec=9 * 3600 + 120,
                )
            ],
            "C": [],
        }
    )

    result = td_dijkstra(
        graph=graph,
        start_id="A",
        goal_id="C",
        depart_time_str="09:00:00",
        transfer_penalty_sec=300,
        route_change_penalty_sec=None,
    )

    assert result.arrival_time_sec == 9 * 3600 + 120
    assert result.stop_path == ["A", "B", "C"]
