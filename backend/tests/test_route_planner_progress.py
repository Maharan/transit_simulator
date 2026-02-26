from __future__ import annotations

from types import SimpleNamespace

import core.routing.route_planner as route_planner
from core.routing.route_planner import EndpointCandidate, RoutePlannerRequest
from core.routing.td_dijkstra import PathResult


class _FakeGraph:
    def __init__(self) -> None:
        self.nodes = {
            "A::trip-1": {"stop_id": "A"},
            "B::trip-1": {"stop_id": "B"},
        }

    def route_stop_ids_for_stop(self, stop_id: str) -> set[str]:
        if stop_id == "A":
            return {"A::trip-1"}
        if stop_id == "B":
            return {"B::trip-1"}
        return set()


class _FakeMultiNodeGraph:
    def __init__(self) -> None:
        self.nodes = {
            "A::trip-1": {"stop_id": "A"},
            "A::trip-2": {"stop_id": "A"},
            "A2::trip-1": {"stop_id": "A2"},
            "B::trip-1": {"stop_id": "B"},
            "B::trip-2": {"stop_id": "B"},
            "B::trip-3": {"stop_id": "B"},
            "B2::trip-1": {"stop_id": "B2"},
        }

    def route_stop_ids_for_stop(self, stop_id: str) -> set[str]:
        if stop_id == "A":
            return {"A::trip-1", "A::trip-2"}
        if stop_id == "A2":
            return {"A2::trip-1"}
        if stop_id == "B":
            return {"B::trip-1", "B::trip-2", "B::trip-3"}
        if stop_id == "B2":
            return {"B2::trip-1"}
        return set()


def test_find_best_route_progress_passes_through_and_prints(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        route_planner, "resolve_feed_id", lambda _session, feed_id: feed_id
    )

    def fake_resolve_endpoint_candidates(*, endpoint_name: str, **_kwargs):
        stop_id = "A" if endpoint_name == "from" else "B"
        return [
            EndpointCandidate(
                stop_id=stop_id,
                stop_name=stop_id,
                parent_id=stop_id,
                parent_name=stop_id,
                walk_distance_m=0.0,
                walk_time_sec=0,
            )
        ]

    monkeypatch.setattr(
        route_planner,
        "_resolve_endpoint_candidates",
        fake_resolve_endpoint_candidates,
    )

    captured: dict[str, object] = {}

    def fake_access_or_create_graph_cache(**kwargs):
        captured["progress"] = kwargs["progress"]
        captured["progress_every"] = kwargs["progress_every"]
        return _FakeGraph(), []

    monkeypatch.setattr(
        route_planner,
        "access_or_create_graph_cache",
        fake_access_or_create_graph_cache,
    )
    monkeypatch.setattr(
        route_planner,
        "td_dijkstra",
        lambda **_kwargs: PathResult(
            arrival_time_sec=120,
            stop_path=["A::trip-1", "B::trip-1"],
            edge_path=[],
        ),
    )
    monkeypatch.setattr(
        route_planner,
        "create_itinerary_data",
        lambda **_kwargs: ({"A": "A", "B": "B"}, {}, {}),
    )
    monkeypatch.setattr(
        route_planner,
        "create_itinerary",
        lambda **_kwargs: SimpleNamespace(summary="summary", timing="timing"),
    )

    _ = route_planner.find_best_route_and_itinerary(
        session=object(),
        request=RoutePlannerRequest(
            from_stop_id="A",
            to_stop_id="B",
            feed_id="feed-1",
            graph_cache_path=None,
            debug_progress=True,
            debug_progress_every=1,
        ),
    )

    assert captured["progress"] is True
    assert captured["progress_every"] == 1

    output = capsys.readouterr().out
    assert "Routing progress: evaluating transit graph searches..." in output
    assert "Routing progress: evaluated 1 search(es);" in output
    assert "Routing progress: completed 1 search(es);" in output


def test_find_best_route_uses_one_global_search_for_all_candidate_pairs(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        route_planner, "resolve_feed_id", lambda _session, feed_id: feed_id
    )

    def fake_resolve_endpoint_candidates(*, endpoint_name: str, **_kwargs):
        if endpoint_name == "from":
            return [
                EndpointCandidate(
                    stop_id="A",
                    stop_name="A",
                    parent_id="A",
                    parent_name="A",
                    walk_distance_m=200.0,
                    walk_time_sec=300,
                ),
                EndpointCandidate(
                    stop_id="A2",
                    stop_name="A2",
                    parent_id="A2",
                    parent_name="A2",
                    walk_distance_m=20.0,
                    walk_time_sec=30,
                ),
            ]
        return [
            EndpointCandidate(
                stop_id="B",
                stop_name="B",
                parent_id="B",
                parent_name="B",
                walk_distance_m=300.0,
                walk_time_sec=400,
            ),
            EndpointCandidate(
                stop_id="B2",
                stop_name="B2",
                parent_id="B2",
                parent_name="B2",
                walk_distance_m=25.0,
                walk_time_sec=35,
            ),
        ]

    monkeypatch.setattr(
        route_planner,
        "_resolve_endpoint_candidates",
        fake_resolve_endpoint_candidates,
    )
    monkeypatch.setattr(
        route_planner,
        "access_or_create_graph_cache",
        lambda **_kwargs: (_FakeMultiNodeGraph(), []),
    )

    captured_calls: list[tuple[str, str]] = []

    def fake_td_dijkstra(**kwargs):
        captured_calls.append((kwargs["start_id"], kwargs["goal_id"]))
        return PathResult(
            arrival_time_sec=200,
            stop_path=[
                kwargs["start_id"],
                "A2::trip-1",
                "B2::trip-1",
                kwargs["goal_id"],
            ],
            edge_path=["source-edge", "edge-1", "sink-edge"],
        )

    monkeypatch.setattr(route_planner, "td_dijkstra", fake_td_dijkstra)
    monkeypatch.setattr(
        route_planner,
        "create_itinerary_data",
        lambda **_kwargs: ({"A": "A", "B": "B"}, {}, {}),
    )
    monkeypatch.setattr(
        route_planner,
        "create_itinerary",
        lambda **_kwargs: SimpleNamespace(summary="summary", timing="timing"),
    )

    result = route_planner.find_best_route_and_itinerary(
        session=object(),
        request=RoutePlannerRequest(
            from_stop_id="A",
            to_stop_id="B",
            feed_id="feed-1",
            graph_cache_path=None,
        ),
    )

    assert len(captured_calls) == 1
    assert captured_calls[0][0].startswith(route_planner.QUERY_SOURCE_NODE_PREFIX)
    assert all(
        goal_id.startswith(route_planner.QUERY_SINK_NODE_PREFIX)
        for _, goal_id in captured_calls
    )
    assert result.context_lines == ["Evaluated transit graph search(es): 1."]
    assert result.best_plan.from_candidate.parent_id == "A2"
    assert result.best_plan.to_candidate.parent_id == "B2"
