from __future__ import annotations

from fastapi.testclient import TestClient

import core.server.fastapi_app as fastapi_app_module
import core.server.route_service as route_service_module
from core.server.serializers import RouteRequest as ApiRouteRequest
import scripts.route_server as route_server
from core.routing.route_planner import EndpointCandidate, RoutePlan, RoutePlannerRequest
from core.routing.td_dijkstra import PathResult
from core.user_facing.itinerary import Itinerary, ItineraryLeg


class _FakeSession:
    def close(self) -> None:
        return


class _FakeDatabase:
    def session(self) -> _FakeSession:
        return _FakeSession()


def test_request_from_payload_uses_server_defaults(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args(["--feed-id", "feed-default"])
    service = route_service_module.RouteService(args)

    request = service._request_from_payload(
        ApiRouteRequest(
            from_lat=53.549053,
            from_lon=9.989263,
            to_lat=53.582231,
            to_lon=10.067991,
        )
    )

    assert request.feed_id == "feed-default"
    assert request.graph_cache_path is not None
    assert request.graph_cache_path.as_posix().endswith(".cache/graph.pkl")
    assert request.depart_time == args.depart_time
    assert request.transfer_penalty_sec == 0
    assert request.route_change_penalty_sec == 300


def test_route_uses_in_memory_graph_cache(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)
    monkeypatch.setattr(
        service,
        "_request_from_payload",
        lambda _payload: RoutePlannerRequest(
            from_stop_name="Origin",
            to_stop_name="Destination",
            feed_id="feed-1",
        ),
    )

    captured = {}

    def fake_find_best_route_and_itinerary(
        *,
        session,
        request,
        in_memory_graph_cache=None,
    ):
        captured["session"] = session
        captured["request"] = request
        captured["in_memory_graph_cache"] = in_memory_graph_cache
        candidate = EndpointCandidate(
            stop_id="S1",
            stop_name="Stop 1",
            parent_id="S1",
            parent_name="Stop 1",
            walk_distance_m=0.0,
            walk_time_sec=0,
        )
        return type(
            "FakeRoutePlannerResult",
            (),
            {
                "feed_id": "feed-1",
                "cache_logs": [],
                "context_lines": [],
                "best_plan": RoutePlan(
                    from_candidate=candidate,
                    to_candidate=candidate,
                    transit_result=PathResult(
                        arrival_time_sec=100,
                        stop_path=["S1"],
                        edge_path=[],
                    ),
                    transit_depart_time_sec=0,
                    arrival_time_sec=100,
                ),
                "itinerary": Itinerary(
                    summary="summary",
                    timing="timing",
                    path_lines=[],
                    leg_lines=[],
                ),
            },
        )()

    monkeypatch.setattr(
        route_service_module,
        "find_best_route_and_itinerary",
        fake_find_best_route_and_itinerary,
    )

    response = service.route(
        ApiRouteRequest(
            from_lat=53.549053,
            from_lon=9.989263,
            to_lat=53.582231,
            to_lon=10.067991,
        )
    )
    assert response["feed_id"] == "feed-1"
    assert captured["request"].from_stop_name == "Origin"
    assert captured["in_memory_graph_cache"] is not None


def test_route_uses_structured_legs_from_itinerary(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)
    monkeypatch.setattr(
        service,
        "_request_from_payload",
        lambda _payload: RoutePlannerRequest(
            from_stop_name="Origin",
            to_stop_name="Destination",
            feed_id="feed-1",
        ),
    )

    candidate = EndpointCandidate(
        stop_id="S1",
        stop_name="Stop 1",
        parent_id="S1",
        parent_name="Stop 1",
        walk_distance_m=0.0,
        walk_time_sec=0,
    )

    def fake_find_best_route_and_itinerary(
        *,
        session,
        request,
        in_memory_graph_cache=None,
    ):
        return type(
            "FakeRoutePlannerResult",
            (),
            {
                "feed_id": "feed-1",
                "cache_logs": [],
                "context_lines": [],
                "best_plan": RoutePlan(
                    from_candidate=candidate,
                    to_candidate=candidate,
                    transit_result=PathResult(
                        arrival_time_sec=100,
                        stop_path=["S1"],
                        edge_path=[],
                    ),
                    transit_depart_time_sec=0,
                    arrival_time_sec=100,
                ),
                "itinerary": Itinerary(
                    summary="summary",
                    timing="timing",
                    path_lines=[],
                    leg_lines=["  this should not be parsed"],
                    legs=[
                        ItineraryLeg(
                            mode="walk",
                            from_stop="A",
                            to_stop="B",
                            route=None,
                            duration_sec=14,
                            duration_min=0.2,
                            text="Walk from A to B (14s (0.2 min))",
                        )
                    ],
                ),
            },
        )()

    monkeypatch.setattr(
        route_service_module,
        "find_best_route_and_itinerary",
        fake_find_best_route_and_itinerary,
    )

    response = service.route(
        ApiRouteRequest(
            from_lat=53.549053,
            from_lon=9.989263,
            to_lat=53.582231,
            to_lon=10.067991,
        )
    )
    assert response["itinerary"]["legs"][0]["mode"] == "walk"
    assert response["itinerary"]["legs"][0]["from_stop"] == "A"


def test_fastapi_health_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)
    app = fastapi_app_module.build_fastapi_app(service)
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_fastapi_route_endpoint_returns_400_on_system_exit(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)
    monkeypatch.setattr(
        service,
        "route",
        lambda _payload: (_ for _ in ()).throw(SystemExit("bad request")),
    )
    app = fastapi_app_module.build_fastapi_app(service)
    client = TestClient(app)

    response = client.post(
        "/route",
        json={
            "from_lat": 53.549053,
            "from_lon": 9.989263,
            "to_lat": 53.582231,
            "to_lon": 10.067991,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "bad request"


def test_fastapi_route_endpoint_returns_typed_payload(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)
    monkeypatch.setattr(
        service,
        "route",
        lambda _payload: {
            "feed_id": "feed-1",
            "cache_logs": [],
            "context_lines": ["Access walk: 10m (14s) to A (S1)"],
            "itinerary": {
                "summary": "summary",
                "timing": "timing",
                "stops": [{"stop_id": "S1", "stop_name": "A"}],
                "path_segments": [
                    {
                        "from_stop": {"stop_id": "S1", "stop_name": "A"},
                        "to_stop": {"stop_id": "S2", "stop_name": "B"},
                        "edge": {
                            "kind": "trip",
                            "label": None,
                            "weight_sec": 60,
                            "route": "U1",
                            "route_id": "R1",
                            "trip_id": "T1",
                            "dep_time": "09:00:00",
                            "arr_time": "09:01:00",
                            "dep_time_sec": 32400,
                            "arr_time_sec": 32460,
                            "transfer_type": None,
                            "apply_penalty": True,
                        },
                    }
                ],
                "legs": [
                    {
                        "mode": "walk",
                        "from_stop": "A",
                        "to_stop": "B",
                        "route": None,
                        "duration_sec": 14,
                        "duration_min": 0.2,
                        "text": "Walk from A to B (14s (0.2 min))",
                    }
                ],
            },
            "best_plan": {
                "from_candidate": {
                    "stop_id": "S1",
                    "stop_name": "A",
                    "parent_id": "S1",
                    "parent_name": "A",
                    "walk_distance_m": 10.0,
                    "walk_time_sec": 14,
                },
                "to_candidate": {
                    "stop_id": "S2",
                    "stop_name": "B",
                    "parent_id": "S2",
                    "parent_name": "B",
                    "walk_distance_m": 20.0,
                    "walk_time_sec": 29,
                },
                "transit_result": {
                    "arrival_time_sec": 100,
                    "stop_path": ["S1", "S2"],
                    "edge_path": [
                        {"to_stop_id": "S2", "weight_sec": 60, "kind": "trip"}
                    ],
                },
                "transit_depart_time_sec": 0,
                "arrival_time_sec": 100,
            },
        },
    )
    app = fastapi_app_module.build_fastapi_app(service)
    client = TestClient(app)

    response = client.post(
        "/route",
        json={
            "from_lat": 53.549053,
            "from_lon": 9.989263,
            "to_lat": 53.582231,
            "to_lon": 10.067991,
        },
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["feed_id"] == "feed-1"
    assert payload["itinerary"]["legs"][0]["mode"] == "walk"
    assert payload["itinerary"]["path_segments"][0]["edge"]["kind"] == "trip"
    assert payload["best_plan"]["to_candidate"]["stop_id"] == "S2"
    assert payload["best_plan"]["transit_result"]["edge_path"][0]["kind"] == "trip"


def test_fastapi_reload_graph_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)
    monkeypatch.setattr(
        service,
        "preload",
        lambda rebuild: ["rebuilt" if rebuild else "loaded"],
    )
    app = fastapi_app_module.build_fastapi_app(service)
    client = TestClient(app)

    response = client.post("/reload-graph", json={"rebuild": True})
    assert response.status_code == 200
    assert response.json() == {"cache_logs": ["rebuilt"]}


def test_server_parser_defaults_for_routing_preferences() -> None:
    args = route_server._build_parser().parse_args([])
    assert args.graph_cache == ".cache/graph.pkl"
    assert args.transfer_penalty == 0
    assert args.route_change_penalty == 300
