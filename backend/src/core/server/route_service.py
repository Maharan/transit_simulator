from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.graph.caching import InMemoryGraphCache, access_or_create_graph_cache
from core.gtfs.utils import resolve_feed_id
from core.routing.route_planner import (
    RoutePlannerRequest,
    find_best_route_and_itinerary,
)
from infra import Database

from .serializers import RouteRequest as RoutePayload


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
        finally:
            session.close()
        itinerary = result.itinerary
        best_plan_data = asdict(result.best_plan)
        self._normalize_best_plan_edge_fields(best_plan_data)
        return {
            "feed_id": result.feed_id,
            "cache_logs": result.cache_logs,
            "context_lines": result.context_lines,
            "itinerary": {
                "summary": itinerary.summary,
                "timing": itinerary.timing,
                "stops": [asdict(stop) for stop in itinerary.stops],
                "path_segments": [
                    asdict(segment) for segment in itinerary.path_segments
                ],
                "legs": [asdict(leg) for leg in itinerary.legs],
            },
            "best_plan": best_plan_data,
        }

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
