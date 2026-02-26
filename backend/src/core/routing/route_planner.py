from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from core.graph.caching import (
    DEFAULT_GRAPH_METHOD,
    InMemoryGraphCache,
    access_or_create_graph_cache,
)
from core.graph.utils import resolve_parent_stop
from core.gtfs.models import Stop
from core.gtfs.utils import (
    resolve_feed_id,
    resolve_stop_by_name,
    resolve_stops_by_coordinates,
)
from core.routing.td_dijkstra import ChosenEdge, PathResult, td_dijkstra
from core.routing.utils import parse_time_to_seconds, seconds_to_time_str
from core.user_facing.itinerary import (
    Itinerary,
    create_itinerary,
    create_itinerary_data,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


COORD_ORIGIN_STOP_ID = "__coord_origin__"
COORD_DEST_STOP_ID = "__coord_destination__"
QUERY_SOURCE_NODE_PREFIX = "__query_source__"
QUERY_SINK_NODE_PREFIX = "__query_sink__"


@dataclass(frozen=True)
class _QuerySinkEdge:
    to_stop_id: str
    weight_sec: int | None = 0
    kind: str = "transfer"
    trip_id: str | None = None
    route_id: str | None = None
    dep_time: str | None = None
    arr_time: str | None = None
    dep_time_sec: int | None = None
    arr_time_sec: int | None = None
    transfer_type: int | None = None
    apply_penalty: bool = False
    label: str | None = "query_sink"


class _QueryAugmentedGraph:
    def __init__(
        self,
        *,
        base_graph,
        source_node_id: str,
        source_edge_weights: dict[str, int],
        sink_node_id: str,
        sink_edge_weights: dict[str, int],
        source_coords: tuple[float, float] | None = None,
        sink_coords: tuple[float, float] | None = None,
    ) -> None:
        self._base_graph = base_graph
        self._source_node_id = source_node_id
        self._sink_node_id = sink_node_id
        self._source_coords = source_coords
        self._sink_coords = sink_coords
        self._source_edges = [
            _QuerySinkEdge(
                to_stop_id=node_id,
                weight_sec=weight_sec,
                label="query_source",
            )
            for node_id, weight_sec in sorted(source_edge_weights.items())
        ]
        self._sink_edges_by_from_node = {
            node_id: _QuerySinkEdge(
                to_stop_id=self._sink_node_id,
                weight_sec=weight_sec,
                label="query_sink",
            )
            for node_id, weight_sec in sink_edge_weights.items()
        }
        self._use_bucket_mode = hasattr(base_graph, "trip_buckets_from") and hasattr(
            base_graph, "transfer_edges_from"
        )

    def edges_from(self, stop_id: str):
        if stop_id == self._source_node_id:
            return self._source_edges
        if stop_id == self._sink_node_id:
            return []
        base_edges = list(self._base_graph.edges_from(stop_id))
        query_sink_edge = self._sink_edges_by_from_node.get(stop_id)
        if query_sink_edge is not None:
            base_edges.append(query_sink_edge)
        return base_edges

    def transfer_edges_from(self, stop_id: str):
        if stop_id == self._source_node_id:
            return self._source_edges
        if stop_id == self._sink_node_id:
            return []
        if not hasattr(self._base_graph, "transfer_edges_from"):
            return []
        base_edges = list(self._base_graph.transfer_edges_from(stop_id))
        query_sink_edge = self._sink_edges_by_from_node.get(stop_id)
        if query_sink_edge is not None:
            base_edges.append(query_sink_edge)
        return base_edges

    def trip_buckets_from(self, stop_id: str):
        if stop_id == self._source_node_id:
            return []
        if stop_id == self._sink_node_id:
            return []
        if not hasattr(self._base_graph, "trip_buckets_from"):
            return []
        return self._base_graph.trip_buckets_from(stop_id)

    def coordinates_for_node(self, stop_id: str) -> tuple[float, float] | None:
        if stop_id == self._source_node_id:
            return self._source_coords
        if stop_id == self._sink_node_id:
            return self._sink_coords
        if hasattr(self._base_graph, "coordinates_for_node"):
            return self._base_graph.coordinates_for_node(stop_id)
        return _node_coords_for_heuristic(self._base_graph, stop_id)

    def __getattr__(self, name: str):
        return getattr(self._base_graph, name)


@dataclass(frozen=True)
class EndpointCandidate:
    stop_id: str
    stop_name: str
    parent_id: str
    parent_name: str
    walk_distance_m: float
    walk_time_sec: int


@dataclass(frozen=True)
class RoutePlan:
    from_candidate: EndpointCandidate
    to_candidate: EndpointCandidate
    transit_result: PathResult
    transit_depart_time_sec: int
    arrival_time_sec: int


@dataclass(frozen=True)
class RoutePlannerRequest:
    from_stop_name: str | None = None
    to_stop_name: str | None = None
    from_stop_id: str | None = None
    to_stop_id: str | None = None
    from_lat: float | None = None
    from_lon: float | None = None
    to_lat: float | None = None
    to_lon: float | None = None
    coord_max_candidates: int = 6
    coord_max_distance_m: float = 500.0
    feed_id: str | None = None
    rebuild: bool = False
    assume_zero_missing: bool = False
    depart_time: str = "09:00:00"
    transfer_penalty_sec: int = 300
    route_change_penalty_sec: int | None = None
    max_wait_sec: int | None = 1200
    state_by: str = "route"
    time_horizon_sec: int = 4 * 3600
    disable_walking: bool = False
    walk_max_distance_m: int = 500
    walk_speed_mps: float = 0.7
    walk_max_neighbors: int = 10
    graph_cache_path: Path | None = None
    rebuild_graph_cache: bool = False
    symmetric_transfers: bool = False
    graph_cache_version: int = 7
    heuristic_max_speed_mps: float | None = 55.0
    graph_method: str = DEFAULT_GRAPH_METHOD
    anytime_default_headway_sec: int | None = None
    debug_progress: bool = False
    debug_progress_every: int = 5000


@dataclass(frozen=True)
class RoutePlannerResult:
    feed_id: str
    cache_logs: list[str]
    context_lines: list[str]
    best_plan: RoutePlan
    itinerary: Itinerary


def find_best_route_and_itinerary(
    *,
    session: "Session",
    request: RoutePlannerRequest,
    in_memory_graph_cache: InMemoryGraphCache | None = None,
) -> RoutePlannerResult:
    feed_id = resolve_feed_id(session, request.feed_id)

    from_mode = _endpoint_mode(
        endpoint_name="from",
        stop_name=request.from_stop_name,
        stop_id=request.from_stop_id,
        lat=request.from_lat,
        lon=request.from_lon,
    )
    to_mode = _endpoint_mode(
        endpoint_name="to",
        stop_name=request.to_stop_name,
        stop_id=request.to_stop_id,
        lat=request.to_lat,
        lon=request.to_lon,
    )
    coords_requested = from_mode == "coords" or to_mode == "coords"

    if request.walk_speed_mps <= 0 and coords_requested:
        raise SystemExit("--walk-speed-mps must be > 0 when using coordinates.")
    if request.coord_max_candidates <= 0:
        raise SystemExit("--coord-max-candidates must be > 0.")
    if request.coord_max_distance_m <= 0:
        raise SystemExit("--coord-max-distance-m must be > 0.")
    if request.max_wait_sec is not None and request.max_wait_sec <= 0:
        raise SystemExit("--max-wait-sec must be > 0 when provided.")
    if (
        request.heuristic_max_speed_mps is not None
        and request.heuristic_max_speed_mps <= 0
    ):
        raise SystemExit("--heuristic-max-speed-mps must be > 0 when provided.")
    if request.debug_progress_every <= 0:
        raise SystemExit("--progress-every must be > 0.")
    if not request.disable_walking:
        if request.walk_max_distance_m <= 0:
            raise SystemExit("--walk-max-distance-m must be > 0.")
        if request.walk_speed_mps <= 0:
            raise SystemExit("--walk-speed-mps must be > 0.")
        if request.walk_max_neighbors <= 0:
            raise SystemExit("--walk-max-neighbors must be > 0.")

    from_candidates = _resolve_endpoint_candidates(
        session=session,
        feed_id=feed_id,
        endpoint_name="from",
        mode=from_mode,
        stop_name=request.from_stop_name,
        stop_id=request.from_stop_id,
        lat=request.from_lat,
        lon=request.from_lon,
        walk_speed_mps=request.walk_speed_mps,
        coord_max_candidates=request.coord_max_candidates,
        coord_max_distance_m=request.coord_max_distance_m,
    )
    to_candidates = _resolve_endpoint_candidates(
        session=session,
        feed_id=feed_id,
        endpoint_name="to",
        mode=to_mode,
        stop_name=request.to_stop_name,
        stop_id=request.to_stop_id,
        lat=request.to_lat,
        lon=request.to_lon,
        walk_speed_mps=request.walk_speed_mps,
        coord_max_candidates=request.coord_max_candidates,
        coord_max_distance_m=request.coord_max_distance_m,
    )

    depart_time_sec = parse_time_to_seconds(request.depart_time)
    if depart_time_sec is None:
        raise SystemExit("Invalid --depart-time. Expected HH:MM:SS.")

    rebuild_cache = request.rebuild or request.rebuild_graph_cache
    graph, cache_logs = access_or_create_graph_cache(
        session=session,
        feed_id=feed_id,
        cache_path=request.graph_cache_path,
        graph_cache_version=request.graph_cache_version,
        rebuild_cache=rebuild_cache,
        symmetric_transfers=request.symmetric_transfers,
        enable_walking=not request.disable_walking,
        walk_max_distance_m=request.walk_max_distance_m,
        walk_speed_mps=request.walk_speed_mps,
        walk_max_neighbors=request.walk_max_neighbors,
        graph_method=request.graph_method,
        anytime_default_headway_sec=request.anytime_default_headway_sec,
        progress=request.debug_progress,
        progress_every=request.debug_progress_every,
        in_memory_cache=in_memory_graph_cache,
    )

    best_plan: RoutePlan | None = None
    evaluated_transit_searches = 0
    if request.debug_progress:
        print("Routing progress: evaluating transit graph searches...")

    source_edge_weights, from_candidate_by_node_id = _query_edge_weights_and_candidates(
        graph=graph,
        candidates=from_candidates,
    )
    sink_edge_weights, to_candidate_by_node_id = _query_edge_weights_and_candidates(
        graph=graph,
        candidates=to_candidates,
    )
    source_coords = _endpoint_coords_for_heuristic(
        graph=graph,
        mode=from_mode,
        lat=request.from_lat,
        lon=request.from_lon,
        candidates=from_candidates,
    )
    sink_coords = _endpoint_coords_for_heuristic(
        graph=graph,
        mode=to_mode,
        lat=request.to_lat,
        lon=request.to_lon,
        candidates=to_candidates,
    )
    if source_edge_weights and sink_edge_weights:
        query_source_node_id = _make_query_source_node_id("all")
        query_sink_node_id = _make_query_sink_node_id("all")
        sink_graph = _QueryAugmentedGraph(
            base_graph=graph,
            source_node_id=query_source_node_id,
            source_edge_weights=source_edge_weights,
            sink_node_id=query_sink_node_id,
            sink_edge_weights=sink_edge_weights,
            source_coords=source_coords,
            sink_coords=sink_coords,
        )
        evaluated_transit_searches = 1
        if (
            request.debug_progress
            and evaluated_transit_searches % request.debug_progress_every == 0
        ):
            print(
                "Routing progress: evaluated "
                f"{evaluated_transit_searches} search(es); no path yet."
            )
        result = td_dijkstra(
            graph=sink_graph,
            start_id=query_source_node_id,
            goal_id=query_sink_node_id,
            depart_time_str=request.depart_time,
            assume_zero_missing=request.assume_zero_missing,
            transfer_penalty_sec=request.transfer_penalty_sec,
            route_change_penalty_sec=request.route_change_penalty_sec,
            time_horizon_sec=request.time_horizon_sec,
            max_wait_sec=request.max_wait_sec,
            state_by=request.state_by,
            heuristic_max_speed_mps=request.heuristic_max_speed_mps,
            debug_progress=request.debug_progress,
            debug_progress_every=request.debug_progress_every,
        )
        if result.arrival_time_sec is not None:
            result_without_query_nodes = _strip_query_terminals_from_result(
                result=result,
                query_source_node_id=query_source_node_id,
                query_sink_node_id=query_sink_node_id,
            )
            first_path_node = (
                result_without_query_nodes.stop_path[0]
                if result_without_query_nodes.stop_path
                else None
            )
            last_path_node = (
                result_without_query_nodes.stop_path[-1]
                if result_without_query_nodes.stop_path
                else None
            )
            from_candidate = (
                from_candidate_by_node_id.get(first_path_node)
                if first_path_node is not None
                else None
            )
            to_candidate = (
                to_candidate_by_node_id.get(last_path_node)
                if last_path_node is not None
                else None
            )
            if from_candidate is None:
                from_candidate = min(
                    from_candidates, key=lambda candidate: candidate.walk_time_sec
                )
            if to_candidate is None:
                to_candidate = min(
                    to_candidates, key=lambda candidate: candidate.walk_time_sec
                )
            best_plan = RoutePlan(
                from_candidate=from_candidate,
                to_candidate=to_candidate,
                transit_result=result_without_query_nodes,
                transit_depart_time_sec=depart_time_sec + from_candidate.walk_time_sec,
                arrival_time_sec=result.arrival_time_sec,
            )

    if request.debug_progress:
        if best_plan is None:
            print(
                "Routing progress: completed "
                f"{evaluated_transit_searches} search(es); no path found."
            )
        else:
            best_arrival = seconds_to_time_str(best_plan.arrival_time_sec) or str(
                best_plan.arrival_time_sec
            )
            print(
                "Routing progress: completed "
                f"{evaluated_transit_searches} search(es); best arrival {best_arrival}."
            )

    if best_plan is None:
        raise SystemExit("No path found for the provided endpoints.")

    itinerary_result = _with_coordinate_walks(
        plan=best_plan,
        from_mode=from_mode,
        to_mode=to_mode,
    )

    display_stop_ids = _display_stop_ids_for_path(
        graph=graph,
        stop_ids=itinerary_result.stop_path,
    )
    stop_names_raw, stop_coords_raw, route_short_names = create_itinerary_data(
        session=session,
        feed_id=feed_id,
        stop_ids=sorted(set(display_stop_ids.values())),
    )
    stop_names = {
        stop_id: stop_names_raw.get(display_stop_id, display_stop_id)
        for stop_id, display_stop_id in display_stop_ids.items()
    }
    stop_coords = {
        stop_id: stop_coords_raw[display_stop_id]
        for stop_id, display_stop_id in display_stop_ids.items()
        if display_stop_id in stop_coords_raw
    }

    from_stop_label = best_plan.from_candidate.parent_name
    to_stop_label = best_plan.to_candidate.parent_name
    if from_mode == "coords":
        from_stop_label = _format_coord_label(request.from_lat, request.from_lon)
        stop_names[COORD_ORIGIN_STOP_ID] = from_stop_label
        if request.from_lat is not None and request.from_lon is not None:
            stop_coords[COORD_ORIGIN_STOP_ID] = (
                float(request.from_lat),
                float(request.from_lon),
            )
    if to_mode == "coords":
        to_stop_label = _format_coord_label(request.to_lat, request.to_lon)
        stop_names[COORD_DEST_STOP_ID] = to_stop_label
        if request.to_lat is not None and request.to_lon is not None:
            stop_coords[COORD_DEST_STOP_ID] = (
                float(request.to_lat),
                float(request.to_lon),
            )

    itinerary = create_itinerary(
        result=itinerary_result,
        from_stop_name=from_stop_label,
        to_stop_name=to_stop_label,
        depart_time_str=request.depart_time,
        stop_names=stop_names,
        stop_coords=stop_coords,
        route_short_names=route_short_names,
        transfer_penalty_sec=request.transfer_penalty_sec,
    )

    context_lines: list[str] = []
    if coords_requested:
        evaluated_pairs = len(from_candidates) * len(to_candidates)
        context_lines.append(
            "Evaluated coordinate candidates: "
            f"{len(from_candidates)} from x {len(to_candidates)} to = {evaluated_pairs} pair(s)."
        )
    if evaluated_transit_searches:
        context_lines.append(
            f"Evaluated transit graph search(es): {evaluated_transit_searches}."
        )
    if from_mode == "coords":
        context_lines.append(
            "Access walk: "
            f"{best_plan.from_candidate.walk_distance_m:.0f}m "
            f"({best_plan.from_candidate.walk_time_sec}s) "
            f"to {best_plan.from_candidate.stop_name} "
            f"({best_plan.from_candidate.stop_id})"
        )
    if to_mode == "coords":
        context_lines.append(
            "Egress walk: "
            f"{best_plan.to_candidate.walk_distance_m:.0f}m "
            f"({best_plan.to_candidate.walk_time_sec}s) "
            f"from {best_plan.to_candidate.stop_name} "
            f"({best_plan.to_candidate.stop_id})"
        )

    return RoutePlannerResult(
        feed_id=feed_id,
        cache_logs=cache_logs,
        context_lines=context_lines,
        best_plan=best_plan,
        itinerary=itinerary,
    )


def _with_coordinate_walks(
    *,
    plan: RoutePlan,
    from_mode: str,
    to_mode: str,
) -> PathResult:
    itinerary_stop_path = list(plan.transit_result.stop_path)
    itinerary_edge_path = list(plan.transit_result.edge_path)

    if from_mode == "coords" and itinerary_stop_path:
        itinerary_edge_path.insert(
            0,
            ChosenEdge(
                to_stop_id=itinerary_stop_path[0],
                weight_sec=plan.from_candidate.walk_time_sec,
                kind="transfer",
                trip_id=None,
                route_id=None,
                dep_time=None,
                arr_time=None,
                dep_time_sec=None,
                arr_time_sec=None,
                transfer_type=None,
                apply_penalty=False,
                label="walk",
            ),
        )
        itinerary_stop_path.insert(0, COORD_ORIGIN_STOP_ID)

    if to_mode == "coords" and itinerary_stop_path:
        itinerary_edge_path.append(
            ChosenEdge(
                to_stop_id=COORD_DEST_STOP_ID,
                weight_sec=plan.to_candidate.walk_time_sec,
                kind="transfer",
                trip_id=None,
                route_id=None,
                dep_time=None,
                arr_time=None,
                dep_time_sec=None,
                arr_time_sec=None,
                transfer_type=None,
                apply_penalty=False,
                label="walk",
            )
        )
        itinerary_stop_path.append(COORD_DEST_STOP_ID)

    return PathResult(
        arrival_time_sec=plan.arrival_time_sec,
        stop_path=itinerary_stop_path,
        edge_path=itinerary_edge_path,
    )


def _endpoint_mode(
    *,
    endpoint_name: str,
    stop_name: str | None,
    stop_id: str | None,
    lat: float | None,
    lon: float | None,
) -> str:
    has_name = bool(stop_name)
    has_id = bool(stop_id)
    has_lat = lat is not None
    has_lon = lon is not None
    if (has_lat or has_lon) and not (has_lat and has_lon):
        raise SystemExit(
            f"--{endpoint_name}-lat and --{endpoint_name}-lon must be provided together."
        )
    if has_id and has_lat and has_lon:
        raise SystemExit(
            f"Use either --{endpoint_name}-stop-id or coordinates, not both."
        )
    if has_id:
        return "id"
    if has_lat and has_lon:
        return "coords"
    if has_name:
        return "name"
    raise SystemExit(
        f"Provide {endpoint_name} endpoint via name, --{endpoint_name}-stop-id, "
        f"or --{endpoint_name}-lat/--{endpoint_name}-lon."
    )


def _resolve_endpoint_candidates(
    *,
    session: "Session",
    feed_id: str,
    endpoint_name: str,
    mode: str,
    stop_name: str | None,
    stop_id: str | None,
    lat: float | None,
    lon: float | None,
    walk_speed_mps: float,
    coord_max_candidates: int,
    coord_max_distance_m: float,
) -> list[EndpointCandidate]:
    if mode == "id":
        row = (
            session.query(Stop.stop_id, Stop.stop_name)
            .filter(Stop.feed_id == feed_id)
            .filter(Stop.stop_id == stop_id)
            .first()
        )
        if not row:
            raise SystemExit(f"Unknown {endpoint_name} stop_id: {stop_id}")
        resolved_stop_id = row[0]
        resolved_stop_name = row[1] or row[0]
        parent_id, parent_name = resolve_parent_stop(session, feed_id, resolved_stop_id)
        return [
            EndpointCandidate(
                stop_id=resolved_stop_id,
                stop_name=resolved_stop_name,
                parent_id=parent_id,
                parent_name=parent_name or resolved_stop_name,
                walk_distance_m=0.0,
                walk_time_sec=0,
            )
        ]

    if mode == "name":
        resolved_stop_id, resolved_stop_name = resolve_stop_by_name(
            session, feed_id, stop_name or ""
        )
        parent_id, parent_name = resolve_parent_stop(session, feed_id, resolved_stop_id)
        return [
            EndpointCandidate(
                stop_id=resolved_stop_id,
                stop_name=resolved_stop_name,
                parent_id=parent_id,
                parent_name=parent_name or resolved_stop_name,
                walk_distance_m=0.0,
                walk_time_sec=0,
            )
        ]

    if lat is None or lon is None:
        raise SystemExit(
            f"--{endpoint_name}-lat and --{endpoint_name}-lon must be provided together."
        )

    raw_matches = resolve_stops_by_coordinates(
        session=session,
        feed_id=feed_id,
        lat=lat,
        lon=lon,
        max_candidates=max(coord_max_candidates * 4, coord_max_candidates),
        max_distance_m=coord_max_distance_m,
    )
    by_parent: dict[str, EndpointCandidate] = {}
    for resolved_stop_id, resolved_stop_name, distance_m in raw_matches:
        parent_id, parent_name = resolve_parent_stop(session, feed_id, resolved_stop_id)
        walk_time_sec = _walk_seconds(distance_m, walk_speed_mps)
        candidate = EndpointCandidate(
            stop_id=resolved_stop_id,
            stop_name=resolved_stop_name,
            parent_id=parent_id,
            parent_name=parent_name or resolved_stop_name,
            walk_distance_m=distance_m,
            walk_time_sec=walk_time_sec,
        )
        existing = by_parent.get(parent_id)
        if existing is None or candidate.walk_distance_m < existing.walk_distance_m:
            by_parent[parent_id] = candidate

    candidates = sorted(by_parent.values(), key=lambda item: item.walk_distance_m)
    candidates = candidates[:coord_max_candidates]
    if not candidates:
        raise SystemExit(
            f"No {endpoint_name} stop candidates found near ({lat:.6f}, {lon:.6f})."
        )
    return candidates


def _walk_seconds(distance_m: float, speed_mps: float) -> int:
    return max(0, int(round(distance_m / speed_mps)))


def _format_coord_label(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "Coordinate"
    return f"Coordinate ({lat:.6f}, {lon:.6f})"


def _make_query_source_node_id(stop_id: str) -> str:
    return f"{QUERY_SOURCE_NODE_PREFIX}::{stop_id}"


def _make_query_sink_node_id(stop_id: str) -> str:
    return f"{QUERY_SINK_NODE_PREFIX}::{stop_id}"


def _strip_query_terminals_from_result(
    *,
    result: PathResult,
    query_source_node_id: str,
    query_sink_node_id: str,
) -> PathResult:
    trimmed_stop_path = list(result.stop_path)
    trimmed_edge_path = list(result.edge_path)

    if trimmed_stop_path and trimmed_stop_path[0] == query_source_node_id:
        trimmed_stop_path = trimmed_stop_path[1:]
        if trimmed_edge_path:
            trimmed_edge_path = trimmed_edge_path[1:]

    if trimmed_stop_path and trimmed_stop_path[-1] == query_sink_node_id:
        trimmed_stop_path = trimmed_stop_path[:-1]
        if trimmed_edge_path:
            trimmed_edge_path = trimmed_edge_path[:-1]

    return PathResult(
        arrival_time_sec=result.arrival_time_sec,
        stop_path=trimmed_stop_path,
        edge_path=trimmed_edge_path,
    )


def _graph_node_ids_for_stop(graph, stop_id: str) -> list[str]:
    if hasattr(graph, "route_stop_ids_for_stop"):
        route_stop_ids = graph.route_stop_ids_for_stop(stop_id)
        if route_stop_ids:
            return sorted(route_stop_ids)
    return [stop_id]


def _query_edge_weights_and_candidates(
    *,
    graph,
    candidates: list[EndpointCandidate],
) -> tuple[dict[str, int], dict[str, EndpointCandidate]]:
    edge_weights: dict[str, int] = {}
    candidate_by_node_id: dict[str, EndpointCandidate] = {}
    for candidate in candidates:
        node_ids = _graph_node_ids_for_stop(graph, candidate.parent_id)
        for node_id in node_ids:
            existing_weight = edge_weights.get(node_id)
            if existing_weight is None or candidate.walk_time_sec < existing_weight:
                edge_weights[node_id] = candidate.walk_time_sec
                candidate_by_node_id[node_id] = candidate
    return edge_weights, candidate_by_node_id


def _node_coords_for_heuristic(graph, node_id: str) -> tuple[float, float] | None:
    if hasattr(graph, "coordinates_for_node"):
        coords = graph.coordinates_for_node(node_id)
        if (
            isinstance(coords, tuple)
            and len(coords) == 2
            and isinstance(coords[0], (int, float))
            and isinstance(coords[1], (int, float))
        ):
            return float(coords[0]), float(coords[1])

    graph_nodes = getattr(graph, "nodes", None)
    if not isinstance(graph_nodes, dict):
        return None
    node_data = graph_nodes.get(node_id)
    if not isinstance(node_data, dict):
        return None
    lat = node_data.get("stop_lat")
    lon = node_data.get("stop_lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    return float(lat), float(lon)


def _endpoint_coords_for_heuristic(
    *,
    graph,
    mode: str,
    lat: float | None,
    lon: float | None,
    candidates: list[EndpointCandidate],
) -> tuple[float, float] | None:
    if mode == "coords" and lat is not None and lon is not None:
        return float(lat), float(lon)

    for candidate in candidates:
        node_ids = _graph_node_ids_for_stop(graph, candidate.parent_id)
        for node_id in node_ids:
            coords = _node_coords_for_heuristic(graph, node_id)
            if coords is not None:
                return coords
    return None


def _display_stop_ids_for_path(*, graph, stop_ids: list[str]) -> dict[str, str]:
    display_stop_ids: dict[str, str] = {}
    graph_nodes = getattr(graph, "nodes", None)
    for stop_id in stop_ids:
        if stop_id in {COORD_ORIGIN_STOP_ID, COORD_DEST_STOP_ID}:
            continue
        if stop_id.startswith((QUERY_SOURCE_NODE_PREFIX, QUERY_SINK_NODE_PREFIX)):
            continue
        display_stop_id = stop_id
        if isinstance(graph_nodes, dict):
            node_data = graph_nodes.get(stop_id)
            if isinstance(node_data, dict):
                node_stop_id = node_data.get("stop_id")
                if isinstance(node_stop_id, str) and node_stop_id:
                    display_stop_id = node_stop_id
        if display_stop_id == stop_id and "::" in stop_id:
            display_stop_id = stop_id.split("::", 1)[0]
        display_stop_ids[stop_id] = display_stop_id
    return display_stop_ids
