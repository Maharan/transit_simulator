from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from core.graph.caching import InMemoryGraphCache, access_or_create_graph_cache
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
    state_by: str = "route"
    time_horizon_sec: int = 4 * 3600
    disable_walking: bool = False
    walk_max_distance_m: int = 500
    walk_speed_mps: float = 0.7
    walk_max_neighbors: int = 10
    graph_cache_path: Path | None = None
    rebuild_graph_cache: bool = False
    symmetric_transfers: bool = False
    graph_cache_version: int = 6


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
        in_memory_cache=in_memory_graph_cache,
    )

    best_plan: RoutePlan | None = None
    for from_candidate in from_candidates:
        transit_depart_time_sec = depart_time_sec + from_candidate.walk_time_sec
        transit_depart_time_str = seconds_to_time_str(transit_depart_time_sec)
        if transit_depart_time_str is None:
            continue
        for to_candidate in to_candidates:
            result = td_dijkstra(
                graph=graph,
                start_id=from_candidate.parent_id,
                goal_id=to_candidate.parent_id,
                depart_time_str=transit_depart_time_str,
                assume_zero_missing=request.assume_zero_missing,
                transfer_penalty_sec=request.transfer_penalty_sec,
                route_change_penalty_sec=request.route_change_penalty_sec,
                time_horizon_sec=request.time_horizon_sec,
                state_by=request.state_by,
            )
            if result.arrival_time_sec is None:
                continue
            arrival_time_sec = result.arrival_time_sec + to_candidate.walk_time_sec
            if best_plan is None or arrival_time_sec < best_plan.arrival_time_sec:
                best_plan = RoutePlan(
                    from_candidate=from_candidate,
                    to_candidate=to_candidate,
                    transit_result=result,
                    transit_depart_time_sec=transit_depart_time_sec,
                    arrival_time_sec=arrival_time_sec,
                )

    if best_plan is None:
        raise SystemExit("No path found for the provided endpoints.")

    itinerary_result = _with_coordinate_walks(
        plan=best_plan,
        from_mode=from_mode,
        to_mode=to_mode,
    )

    stop_names, route_short_names = create_itinerary_data(
        session=session,
        feed_id=feed_id,
        stop_ids=itinerary_result.stop_path,
    )

    from_stop_label = best_plan.from_candidate.parent_name
    to_stop_label = best_plan.to_candidate.parent_name
    if from_mode == "coords":
        from_stop_label = _format_coord_label(request.from_lat, request.from_lon)
        stop_names[COORD_ORIGIN_STOP_ID] = from_stop_label
    if to_mode == "coords":
        to_stop_label = _format_coord_label(request.to_lat, request.to_lon)
        stop_names[COORD_DEST_STOP_ID] = to_stop_label

    itinerary = create_itinerary(
        result=itinerary_result,
        from_stop_name=from_stop_label,
        to_stop_name=to_stop_label,
        depart_time_str=request.depart_time,
        stop_names=stop_names,
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
