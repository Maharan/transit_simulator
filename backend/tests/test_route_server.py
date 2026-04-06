from __future__ import annotations

from fastapi.testclient import TestClient

import core.server.fastapi_app as fastapi_app_module
import core.server.route_service as route_service_module
from core.server.serializers import RouteRequest as ApiRouteRequest
from core.graph.graph_methods.trip_stop_graph import TripStopEdge
import scripts.route_server as route_server
from core.routing.route_planner import (
    EndpointCandidate,
    RouteOption,
    RoutePlan,
    RoutePlannerRequest,
)
from core.routing.td_dijkstra import PathResult
from core.user_facing.itinerary import (
    Itinerary,
    ItineraryLeg,
    ItineraryPathEdge,
    ItineraryPathSegment,
    ItineraryStop,
)


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
    assert request.route_change_penalty_sec == 0
    assert request.max_wait_sec == 1200
    assert request.max_rounds == 8
    assert request.max_major_transfers == 4
    assert request.graph_method == "trip_stop"


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


def test_route_serializes_route_options_and_best_option_index(monkeypatch) -> None:
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
        option_a = RouteOption(
            best_plan=RoutePlan(
                from_candidate=candidate,
                to_candidate=candidate,
                transit_result=PathResult(
                    arrival_time_sec=200,
                    stop_path=["S1"],
                    edge_path=[],
                ),
                transit_depart_time_sec=0,
                arrival_time_sec=200,
            ),
            itinerary=Itinerary(
                summary="Option A",
                timing="timing-a",
                path_lines=[],
                leg_lines=[],
            ),
            major_trip_transfers=0,
            transit_legs=1,
        )
        option_b = RouteOption(
            best_plan=RoutePlan(
                from_candidate=candidate,
                to_candidate=candidate,
                transit_result=PathResult(
                    arrival_time_sec=150,
                    stop_path=["S1"],
                    edge_path=[],
                ),
                transit_depart_time_sec=0,
                arrival_time_sec=150,
            ),
            itinerary=Itinerary(
                summary="Option B",
                timing="timing-b",
                path_lines=[],
                leg_lines=[],
            ),
            major_trip_transfers=1,
            transit_legs=2,
        )
        return type(
            "FakeRoutePlannerResult",
            (),
            {
                "feed_id": "feed-1",
                "cache_logs": [],
                "context_lines": ["Pareto-optimal route options: 2."],
                "best_plan": option_b.best_plan,
                "itinerary": option_b.itinerary,
                "options": (option_a, option_b),
                "best_option_index": 1,
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

    assert response["best_option_index"] == 1
    assert response["options"][0]["major_trip_transfers"] == 0
    assert response["options"][1]["major_trip_transfers"] == 1
    assert response["itinerary"]["summary"] == "Option B"
    assert response["best_plan"]["arrival_time_sec"] == 150


def test_route_serializes_path_segment_display_color(monkeypatch) -> None:
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

    def fake_attach_path_segment_geometries(*, session, feed_id, path_segments) -> None:
        assert feed_id == "feed-1"
        path_segments[0]["edge"]["display_color"] = "#005AAE"
        path_segments[0]["edge"]["display_text_color"] = "#FFFFFF"

    monkeypatch.setattr(
        route_service_module,
        "attach_path_segment_geometries",
        fake_attach_path_segment_geometries,
    )

    def fake_find_best_route_and_itinerary(
        *,
        session,
        request,
        in_memory_graph_cache=None,
    ):
        path_segment = ItineraryPathSegment(
            from_stop=ItineraryStop(
                stop_id="S1",
                stop_name="A",
                stop_lat=53.55,
                stop_lon=9.99,
            ),
            to_stop=ItineraryStop(
                stop_id="S2",
                stop_name="B",
                stop_lat=53.56,
                stop_lon=10.0,
            ),
            edge=ItineraryPathEdge(
                kind="trip",
                label=None,
                weight_sec=60,
                route="U1",
                route_id="R1",
                trip_id="T1",
                dep_time="09:00:00",
                arr_time="09:01:00",
                dep_time_sec=32400,
                arr_time_sec=32460,
                transfer_type=None,
                apply_penalty=True,
            ),
        )
        route_option = RouteOption(
            best_plan=RoutePlan(
                from_candidate=candidate,
                to_candidate=candidate,
                transit_result=PathResult(
                    arrival_time_sec=100,
                    stop_path=["S1", "S2"],
                    edge_path=[],
                ),
                transit_depart_time_sec=0,
                arrival_time_sec=100,
            ),
            itinerary=Itinerary(
                summary="Option A",
                timing="timing-a",
                path_lines=[],
                leg_lines=[],
                path_segments=[path_segment],
            ),
            major_trip_transfers=0,
            transit_legs=1,
        )
        return type(
            "FakeRoutePlannerResult",
            (),
            {
                "feed_id": "feed-1",
                "cache_logs": [],
                "context_lines": [],
                "best_plan": route_option.best_plan,
                "itinerary": route_option.itinerary,
                "options": (route_option,),
                "best_option_index": 0,
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

    edge = response["itinerary"]["path_segments"][0]["edge"]
    assert edge["display_color"] == "#005AAE"
    assert edge["display_text_color"] == "#FFFFFF"


def test_route_normalizes_trip_stop_edge_to_stop_id_for_best_plan(
    monkeypatch,
) -> None:
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
                        stop_path=["S1", "S2"],
                        edge_path=[
                            TripStopEdge(
                                to_route_stop_id="S2",
                                weight_sec=30,
                                kind="transfer",
                                transfer_type=2,
                                apply_penalty=True,
                                label="station_link",
                            )
                        ],
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

    edge = response["best_plan"]["transit_result"]["edge_path"][0]
    assert edge["to_stop_id"] == "S2"
    assert "to_route_stop_id" not in edge


def test_network_lines_uses_resolved_feed(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args(["--feed-id", "feed-default"])
    service = route_service_module.RouteService(args)

    monkeypatch.setattr(
        route_service_module,
        "resolve_feed_id",
        lambda _session, feed_id: f"{feed_id}-resolved",
    )

    captured: dict[str, str] = {}

    def fake_load_network_lines_geojson(*, session, feed_id: str):
        captured["feed_id"] = feed_id
        return {"type": "FeatureCollection", "features": []}

    monkeypatch.setattr(
        route_service_module,
        "load_network_lines_geojson",
        fake_load_network_lines_geojson,
    )

    payload = service.network_lines()

    assert payload["type"] == "FeatureCollection"
    assert captured["feed_id"] == "feed-default-resolved"


def test_population_grid_passes_through_bounds(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)

    captured: dict[str, float | int] = {}

    def fake_load_population_grid_geojson(
        *,
        session,
        dataset_year: int,
        min_lat: float | None = None,
        min_lon: float | None = None,
        max_lat: float | None = None,
        max_lon: float | None = None,
    ):
        captured["dataset_year"] = dataset_year
        captured["min_lat"] = min_lat if min_lat is not None else -1
        captured["min_lon"] = min_lon if min_lon is not None else -1
        captured["max_lat"] = max_lat if max_lat is not None else -1
        captured["max_lon"] = max_lon if max_lon is not None else -1
        return {"type": "FeatureCollection", "features": []}

    monkeypatch.setattr(
        route_service_module,
        "load_population_grid_geojson",
        fake_load_population_grid_geojson,
    )

    payload = service.population_grid(
        dataset_year=2020,
        min_lat=53.4,
        min_lon=9.7,
        max_lat=53.7,
        max_lon=10.2,
    )

    assert payload["type"] == "FeatureCollection"
    assert captured == {
        "dataset_year": 2020,
        "min_lat": 53.4,
        "min_lon": 9.7,
        "max_lat": 53.7,
        "max_lon": 10.2,
    }


def test_floor_space_density_passes_through_bounds(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)

    captured: dict[str, float | int | str] = {}

    def fake_load_floor_space_density_geojson(
        *,
        session,
        dataset_release: str,
        grid_resolution_m: int,
        min_lat: float | None = None,
        min_lon: float | None = None,
        max_lat: float | None = None,
        max_lon: float | None = None,
    ):
        captured["dataset_release"] = dataset_release
        captured["grid_resolution_m"] = grid_resolution_m
        captured["min_lat"] = min_lat if min_lat is not None else -1
        captured["min_lon"] = min_lon if min_lon is not None else -1
        captured["max_lat"] = max_lat if max_lat is not None else -1
        captured["max_lon"] = max_lon if max_lon is not None else -1
        return {"type": "FeatureCollection", "features": []}

    monkeypatch.setattr(
        route_service_module,
        "load_floor_space_density_geojson",
        fake_load_floor_space_density_geojson,
    )

    payload = service.floor_space_density(
        dataset_release="2023-04-01",
        grid_resolution_m=100,
        min_lat=53.4,
        min_lon=9.7,
        max_lat=53.7,
        max_lon=10.2,
    )

    assert payload["type"] == "FeatureCollection"
    assert captured == {
        "dataset_release": "2023-04-01",
        "grid_resolution_m": 100,
        "min_lat": 53.4,
        "min_lon": 9.7,
        "max_lat": 53.7,
        "max_lon": 10.2,
    }


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
                "stops": [
                    {
                        "stop_id": "S1",
                        "stop_name": "A",
                        "stop_lat": 53.55,
                        "stop_lon": 9.99,
                    }
                ],
                "path_segments": [
                    {
                        "from_stop": {
                            "stop_id": "S1",
                            "stop_name": "A",
                            "stop_lat": 53.55,
                            "stop_lon": 9.99,
                        },
                        "to_stop": {
                            "stop_id": "S2",
                            "stop_name": "B",
                            "stop_lat": 53.56,
                            "stop_lon": 10.0,
                        },
                        "geometry": [[9.99, 53.55], [10.0, 53.56]],
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
            "options": [
                {
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
                    "itinerary": {
                        "summary": "summary",
                        "timing": "timing",
                        "stops": [
                            {
                                "stop_id": "S1",
                                "stop_name": "A",
                                "stop_lat": 53.55,
                                "stop_lon": 9.99,
                            }
                        ],
                        "path_segments": [
                            {
                                "from_stop": {
                                    "stop_id": "S1",
                                    "stop_name": "A",
                                    "stop_lat": 53.55,
                                    "stop_lon": 9.99,
                                },
                                "to_stop": {
                                    "stop_id": "S2",
                                    "stop_name": "B",
                                    "stop_lat": 53.56,
                                    "stop_lon": 10.0,
                                },
                                "geometry": [[9.99, 53.55], [10.0, 53.56]],
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
                    "major_trip_transfers": 0,
                    "transit_legs": 1,
                }
            ],
            "best_option_index": 0,
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
    assert payload["itinerary"]["stops"][0]["stop_lat"] == 53.55
    assert payload["itinerary"]["stops"][0]["stop_lon"] == 9.99
    assert payload["itinerary"]["path_segments"][0]["edge"]["kind"] == "trip"
    assert payload["itinerary"]["path_segments"][0]["geometry"][0] == [9.99, 53.55]
    assert payload["best_plan"]["to_candidate"]["stop_id"] == "S2"
    assert payload["best_plan"]["transit_result"]["edge_path"][0]["kind"] == "trip"
    assert payload["options"][0]["major_trip_transfers"] == 0
    assert payload["best_option_index"] == 0


def test_fastapi_network_lines_endpoint_returns_typed_payload(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)
    monkeypatch.setattr(
        service,
        "network_lines",
        lambda feed_id=None: {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "line_id": "U1",
                        "line_family": "u_bahn",
                        "color": "#005AAE",
                        "offset_px": -3.0,
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[9.95, 53.55], [10.02, 53.58]],
                    },
                }
            ],
        },
    )
    app = fastapi_app_module.build_fastapi_app(service)
    client = TestClient(app)

    response = client.get("/network-lines")
    payload = response.json()

    assert response.status_code == 200
    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["properties"]["line_id"] == "U1"
    assert payload["features"][0]["properties"]["line_family"] == "u_bahn"


def test_fastapi_population_grid_endpoint_returns_typed_payload(monkeypatch) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)
    monkeypatch.setattr(
        service,
        "population_grid",
        lambda **_kwargs: {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "population_estimate": 125.0,
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [9.99, 53.55],
                                [10.0, 53.55],
                                [10.0, 53.56],
                                [9.99, 53.56],
                                [9.99, 53.55],
                            ]
                        ],
                    },
                }
            ],
        },
    )
    app = fastapi_app_module.build_fastapi_app(service)
    client = TestClient(app)

    response = client.get(
        "/population-grid",
        params={
            "dataset_year": 2020,
            "min_lat": 53.4,
            "min_lon": 9.7,
            "max_lat": 53.7,
            "max_lon": 10.2,
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["properties"]["population_estimate"] == 125.0
    assert payload["features"][0]["geometry"]["coordinates"][0][0] == [9.99, 53.55]


def test_fastapi_floor_space_density_endpoint_returns_typed_payload(
    monkeypatch,
) -> None:
    monkeypatch.setattr(route_service_module, "Database", lambda: _FakeDatabase())
    args = route_server._build_parser().parse_args([])
    service = route_service_module.RouteService(args)
    monkeypatch.setattr(
        service,
        "floor_space_density",
        lambda **_kwargs: {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "building_count": 4,
                        "floor_space_m2": 2800.0,
                        "floor_space_density_sqkm": 280000.0,
                        "population_estimate": 140.0,
                        "population_density_sqkm": 14000.0,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [9.99, 53.55],
                    },
                }
            ],
        },
    )
    app = fastapi_app_module.build_fastapi_app(service)
    client = TestClient(app)

    response = client.get(
        "/floor-space-density",
        params={
            "dataset_release": "2023-04-01",
            "grid_resolution_m": 100,
            "min_lat": 53.4,
            "min_lon": 9.7,
            "max_lat": 53.7,
            "max_lon": 10.2,
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["properties"]["floor_space_m2"] == 2800.0
    assert payload["features"][0]["geometry"]["coordinates"] == [9.99, 53.55]


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
    assert args.route_change_penalty == 0
    assert args.max_rounds == 8
    assert args.max_major_transfers == 4
    assert args.graph_method == "trip_stop"
    assert args.progress is False
    assert args.progress_every == 5000
