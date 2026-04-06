from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.graph.caching import InMemoryGraphCache, access_or_create_graph_cache
from core.gtfs.utils import resolve_feed_id
from core.routing.route_planner import (
    RoutePlannerRequest,
    find_best_route_and_itinerary,
)
from infra import Database

from .floor_space_density import load_floor_space_density_geojson
from .network_lines import load_network_lines_geojson
from .population_grid import load_population_grid_geojson
from .segment_shapes import attach_path_segment_geometries
from .serializers import RouteRequest as RoutePayload


@dataclass(frozen=True)
class _RouteOptionLike:
    best_plan: Any
    itinerary: Any
    major_trip_transfers: int
    transit_legs: int


class RouteService:
    def __init__(self, args: argparse.Namespace) -> None:
        self._args = args
        self._database = Database()
        self._graph_cache = InMemoryGraphCache()

    def status(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "default_feed_id": self._args.feed_id,
            "graph_cache_version": self._args.graph_cache_version,
            "default_graph_method": self._args.graph_method,
        }

    def preload(self, *, rebuild: bool) -> list[str]:
        session = self._database.session()
        try:
            feed_id = resolve_feed_id(session, self._args.feed_id)
            _, logs = access_or_create_graph_cache(
                session=session,
                feed_id=feed_id,
                cache_path=Path(self._args.graph_cache)
                if self._args.graph_cache
                else None,
                graph_cache_version=self._args.graph_cache_version,
                rebuild_cache=rebuild,
                symmetric_transfers=self._args.symmetric_transfers,
                enable_walking=not self._args.disable_walking,
                walk_max_distance_m=self._args.walk_max_distance_m,
                walk_speed_mps=self._args.walk_speed_mps,
                walk_max_neighbors=self._args.walk_max_neighbors,
                graph_method=self._args.graph_method,
                anytime_default_headway_sec=self._args.anytime_default_headway_sec,
                progress=bool(getattr(self._args, "progress", False)),
                progress_every=int(getattr(self._args, "progress_every", 5000)),
                in_memory_cache=self._graph_cache,
            )
            return logs
        finally:
            session.close()

    def route(self, payload: RoutePayload | dict[str, Any]) -> dict[str, Any]:
        normalized_payload = (
            payload
            if isinstance(payload, RoutePayload)
            else RoutePayload.model_validate(payload)
        )
        request = self._request_from_payload(normalized_payload)
        session = self._database.session()
        try:
            result = find_best_route_and_itinerary(
                session=session,
                request=request,
                in_memory_graph_cache=self._graph_cache,
            )
            route_options = self._route_options_from_result(result)
            serialized_options = [
                self._serialize_route_option(
                    session=session,
                    feed_id=result.feed_id,
                    option=option,
                )
                for option in route_options
            ]
            if not serialized_options:
                raise ValueError("Route planner returned no route options.")
            best_option_index = int(getattr(result, "best_option_index", 0) or 0)
            if best_option_index < 0 or best_option_index >= len(serialized_options):
                best_option_index = 0
            best_option = serialized_options[best_option_index]
            return {
                "feed_id": result.feed_id,
                "cache_logs": result.cache_logs,
                "context_lines": result.context_lines,
                "itinerary": best_option["itinerary"],
                "best_plan": best_option["best_plan"],
                "options": serialized_options,
                "best_option_index": best_option_index,
            }
        finally:
            session.close()

    def network_lines(self, *, feed_id: str | None = None) -> dict[str, Any]:
        session = self._database.session()
        try:
            resolved_feed_id = resolve_feed_id(session, feed_id or self._args.feed_id)
            return load_network_lines_geojson(session=session, feed_id=resolved_feed_id)
        finally:
            session.close()

    def population_grid(
        self,
        *,
        dataset_year: int = 2020,
        min_lat: float | None = None,
        min_lon: float | None = None,
        max_lat: float | None = None,
        max_lon: float | None = None,
    ) -> dict[str, Any]:
        session = self._database.session()
        try:
            return load_population_grid_geojson(
                session=session,
                dataset_year=dataset_year,
                min_lat=min_lat,
                min_lon=min_lon,
                max_lat=max_lat,
                max_lon=max_lon,
            )
        finally:
            session.close()

    def floor_space_density(
        self,
        *,
        dataset_release: str,
        grid_resolution_m: int = 100,
        min_lat: float | None = None,
        min_lon: float | None = None,
        max_lat: float | None = None,
        max_lon: float | None = None,
    ) -> dict[str, Any]:
        session = self._database.session()
        try:
            return load_floor_space_density_geojson(
                session=session,
                dataset_release=dataset_release,
                grid_resolution_m=grid_resolution_m,
                min_lat=min_lat,
                min_lon=min_lon,
                max_lat=max_lat,
                max_lon=max_lon,
            )
        finally:
            session.close()

    @staticmethod
    def _normalize_best_plan_edge_fields(best_plan_data: dict[str, Any]) -> None:
        transit_result = best_plan_data.get("transit_result")
        if not isinstance(transit_result, dict):
            return
        edge_path = transit_result.get("edge_path")
        if not isinstance(edge_path, list):
            return
        for edge in edge_path:
            if not isinstance(edge, dict):
                continue
            if "to_stop_id" in edge:
                continue
            to_route_stop_id = edge.pop("to_route_stop_id", None)
            if to_route_stop_id is not None:
                edge["to_stop_id"] = to_route_stop_id

    @classmethod
    def _route_options_from_result(cls, result: Any) -> list[_RouteOptionLike]:
        result_options = getattr(result, "options", None)
        if result_options:
            return [
                _RouteOptionLike(
                    best_plan=option.best_plan,
                    itinerary=option.itinerary,
                    major_trip_transfers=int(option.major_trip_transfers),
                    transit_legs=int(option.transit_legs),
                )
                for option in result_options
            ]

        ride_legs = [
            leg
            for leg in getattr(getattr(result, "itinerary", None), "legs", [])
            if getattr(leg, "mode", None) == "ride"
        ]
        return [
            _RouteOptionLike(
                best_plan=result.best_plan,
                itinerary=result.itinerary,
                major_trip_transfers=max(len(ride_legs) - 1, 0),
                transit_legs=len(ride_legs),
            )
        ]

    def _serialize_route_option(
        self,
        *,
        session,
        feed_id: str,
        option: _RouteOptionLike,
    ) -> dict[str, Any]:
        itinerary = option.itinerary
        itinerary_path_segments = [
            asdict(segment) for segment in getattr(itinerary, "path_segments", [])
        ]
        attach_path_segment_geometries(
            session=session,
            feed_id=feed_id,
            path_segments=itinerary_path_segments,
        )

        best_plan_data = asdict(option.best_plan)
        self._normalize_best_plan_edge_fields(best_plan_data)
        return {
            "best_plan": best_plan_data,
            "itinerary": {
                "summary": itinerary.summary,
                "timing": itinerary.timing,
                "stops": [asdict(stop) for stop in getattr(itinerary, "stops", [])],
                "path_segments": itinerary_path_segments,
                "legs": [asdict(leg) for leg in getattr(itinerary, "legs", [])],
            },
            "major_trip_transfers": option.major_trip_transfers,
            "transit_legs": option.transit_legs,
        }

    def _request_from_payload(self, payload: RoutePayload) -> RoutePlannerRequest:
        request_data = self._default_request_data()

        payload_data = payload.model_dump(exclude_none=True)
        graph_cache_value = payload_data.pop("graph_cache_path", None)
        if graph_cache_value:
            payload_data["graph_cache_path"] = Path(str(graph_cache_value))
        elif graph_cache_value is not None:
            payload_data["graph_cache_path"] = None

        request_data.update(payload_data)
        return RoutePlannerRequest(**request_data)

    def _default_request_data(self) -> dict[str, Any]:
        route_request_fields = RoutePlannerRequest.__dataclass_fields__
        request_data: dict[str, Any] = {
            key: value
            for key, value in vars(self._args).items()
            if key in route_request_fields and key != "graph_cache_path"
        }
        request_data.update(
            {
                "transfer_penalty_sec": self._args.transfer_penalty,
                "route_change_penalty_sec": self._args.route_change_penalty,
                "graph_cache_path": Path(self._args.graph_cache)
                if self._args.graph_cache
                else None,
            }
        )
        return request_data
