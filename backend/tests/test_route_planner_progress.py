from __future__ import annotations

from types import SimpleNamespace

import core.routing.route_planner as route_planner
from core.routing.raptor import (
    RaptorJourneyOption,
    RaptorQuery,
    RaptorResult,
    RaptorRoute,
    RaptorTimetable,
    RaptorTrip,
)
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


def _make_raptor_timetable() -> RaptorTimetable:
    route = RaptorRoute(
        route_key="route-1",
        public_route_id="R1",
        stop_ids=("A", "D"),
        trips=(
            RaptorTrip(
                trip_id="trip-1",
                route_id="R1",
                service_id="service-1",
                arrivals=(9 * 3600, 9 * 3600 + 600),
                departures=(9 * 3600, 9 * 3600 + 600),
            ),
        ),
        departures_by_stop=((9 * 3600,), (9 * 3600 + 600,)),
        trip_indices_by_stop=((0,), (0,)),
    )
    return RaptorTimetable(
        routes={"route-1": route},
        stop_to_routes={"A": ("route-1",), "D": ("route-1",)},
        route_stop_indices={
            ("route-1", "A"): (0,),
            ("route-1", "D"): (1,),
        },
        footpaths_from={},
        stops=("A", "D"),
    )


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


def test_find_best_route_uses_raptor_backend(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        route_planner,
        "resolve_feed_id",
        lambda _session, feed_id: feed_id,
    )

    def fake_resolve_endpoint_candidates(*, endpoint_name: str, **_kwargs):
        stop_id = "A" if endpoint_name == "from" else "D"
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
    monkeypatch.setattr(
        route_planner,
        "access_or_create_graph_cache",
        lambda **_kwargs: (_make_raptor_timetable(), []),
    )
    monkeypatch.setattr(
        route_planner,
        "td_dijkstra",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("td_dijkstra should not run for RAPTOR routing.")
        ),
    )
    monkeypatch.setattr(
        route_planner,
        "create_itinerary_data",
        lambda **_kwargs: ({"A": "A", "D": "D"}, {}, {"R1": "R1"}),
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
            to_stop_id="D",
            feed_id="feed-1",
            graph_cache_path=None,
            graph_method="raptor",
            max_rounds=1,
        ),
    )

    assert result.context_lines == ["Evaluated transit graph search(es): 1."]
    assert result.best_plan.transit_result.stop_path == ["A", "D"]
    assert result.best_plan.transit_result.edge_path[0].trip_id == "trip-1"
    assert len(result.options) == 1
    assert result.best_option_index == 0


def test_find_best_route_raptor_does_not_reuse_transfer_penalty_as_route_change_penalty(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        route_planner,
        "resolve_feed_id",
        lambda _session, feed_id: feed_id,
    )

    def fake_resolve_endpoint_candidates(*, endpoint_name: str, **_kwargs):
        stop_id = "A" if endpoint_name == "from" else "D"
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
    monkeypatch.setattr(
        route_planner,
        "access_or_create_graph_cache",
        lambda **_kwargs: (_make_raptor_timetable(), []),
    )
    captured_query: dict[str, RaptorQuery] = {}

    def fake_run_raptor(*, timetable, query):
        captured_query["query"] = query
        path_result = PathResult(
            arrival_time_sec=9 * 3600 + 600,
            stop_path=["A", "D"],
            edge_path=[],
        )
        return RaptorResult(
            path_result=path_result,
            best_target_stop_id="D",
            best_round=1,
            transit_arrival_time_sec=9 * 3600 + 600,
            options=(
                RaptorJourneyOption(
                    path_result=path_result,
                    target_stop_id="D",
                    round_k=1,
                    transit_arrival_time_sec=9 * 3600 + 600,
                    final_arrival_time_sec=9 * 3600 + 600,
                    transit_legs=1,
                    major_trip_transfers=0,
                ),
            ),
        )

    monkeypatch.setattr(route_planner, "run_raptor", fake_run_raptor)
    monkeypatch.setattr(
        route_planner,
        "create_itinerary_data",
        lambda **_kwargs: ({"A": "A", "D": "D"}, {}, {"R1": "R1"}),
    )
    monkeypatch.setattr(
        route_planner,
        "create_itinerary",
        lambda **_kwargs: SimpleNamespace(summary="summary", timing="timing"),
    )

    route_planner.find_best_route_and_itinerary(
        session=object(),
        request=RoutePlannerRequest(
            from_stop_id="A",
            to_stop_id="D",
            feed_id="feed-1",
            graph_cache_path=None,
            graph_method="raptor",
            transfer_penalty_sec=300,
            route_change_penalty_sec=None,
        ),
    )

    assert captured_query["query"].transfer_penalty_sec == 0


def test_find_best_route_raptor_caps_rounds_by_max_major_transfers(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        route_planner,
        "resolve_feed_id",
        lambda _session, feed_id: feed_id,
    )

    def fake_resolve_endpoint_candidates(*, endpoint_name: str, **_kwargs):
        stop_id = "A" if endpoint_name == "from" else "D"
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
    monkeypatch.setattr(
        route_planner,
        "access_or_create_graph_cache",
        lambda **_kwargs: (_make_raptor_timetable(), []),
    )
    captured_query: dict[str, RaptorQuery] = {}

    def fake_run_raptor(*, timetable, query):
        captured_query["query"] = query
        return RaptorResult(
            path_result=PathResult(
                arrival_time_sec=9 * 3600 + 600,
                stop_path=["A", "D"],
                edge_path=[],
            ),
            best_target_stop_id="D",
            best_round=1,
            transit_arrival_time_sec=9 * 3600 + 600,
            options=(),
        )

    monkeypatch.setattr(route_planner, "run_raptor", fake_run_raptor)
    monkeypatch.setattr(
        route_planner,
        "create_itinerary_data",
        lambda **_kwargs: ({"A": "A", "D": "D"}, {}, {"R1": "R1"}),
    )
    monkeypatch.setattr(
        route_planner,
        "create_itinerary",
        lambda **_kwargs: SimpleNamespace(summary="summary", timing="timing"),
    )

    try:
        route_planner.find_best_route_and_itinerary(
            session=object(),
            request=RoutePlannerRequest(
                from_stop_id="A",
                to_stop_id="D",
                feed_id="feed-1",
                graph_cache_path=None,
                graph_method="raptor",
                max_rounds=8,
                max_major_transfers=2,
            ),
        )
    except SystemExit as exc:  # pragma: no cover - defensive for empty fake result.
        assert str(exc) == "No path found for the provided endpoints."

    assert captured_query["query"].max_rounds == 3
