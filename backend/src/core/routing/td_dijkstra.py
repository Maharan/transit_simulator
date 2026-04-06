from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
import heapq
import itertools
import math

from core.routing.types import GraphLike
from core.routing.utils import parse_time_to_seconds, seconds_to_time_str

RIDE_EDGE_KINDS = {"trip", "ride"}
EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class PathResult:
    arrival_time_sec: int | None
    stop_path: list[str]
    edge_path: list


@dataclass(frozen=True)
class ChosenEdge:
    to_stop_id: str
    weight_sec: int | None
    kind: str
    trip_id: str | None
    route_id: str | None
    dep_time: str | None
    arr_time: str | None
    dep_time_sec: int | None
    arr_time_sec: int | None
    transfer_type: int | None
    apply_penalty: bool = True
    label: str | None = None


def _graph_coordinates_for_node(
    graph: GraphLike,
    node_id: str,
) -> tuple[float, float] | None:
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


def _haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def _edge_schedule_seconds(edge) -> tuple[int | None, int | None]:
    dep_sec = getattr(edge, "dep_time_sec", None)
    arr_sec = getattr(edge, "arr_time_sec", None)
    if dep_sec is None or arr_sec is None:
        dep_sec = parse_time_to_seconds(getattr(edge, "dep_time", None))
        arr_sec = parse_time_to_seconds(getattr(edge, "arr_time", None))
    return dep_sec, arr_sec


def _ride_departure_cursor(
    *,
    edge,
    current_time: int,
    assume_zero_missing: bool,
    max_wait_sec: int | None,
) -> int | None:
    dep_sec, arr_sec = _edge_schedule_seconds(edge)
    has_explicit_schedule = dep_sec is not None and arr_sec is not None
    if has_explicit_schedule:
        wait_sec = dep_sec - current_time
        if wait_sec < 0 or arr_sec < dep_sec:
            return None
        if max_wait_sec is not None and wait_sec > max_wait_sec:
            return None
        return dep_sec

    weight_sec = getattr(edge, "weight_sec", None)
    if weight_sec is not None:
        headway_sec = getattr(edge, "headway_sec", None)
        estimated_wait = (
            headway_sec // 2 if isinstance(headway_sec, int) and headway_sec > 0 else 0
        )
        if max_wait_sec is not None and estimated_wait > max_wait_sec:
            return None
        return current_time + estimated_wait

    if assume_zero_missing:
        return current_time
    return None


def _state_group_key_for_ride_edge(*, edge, state_by: str):
    if state_by == "route":
        key = getattr(edge, "route_id", None)
        if key is not None:
            return ("route", key)
        fallback = getattr(edge, "trip_id", None)
        if fallback is not None:
            return ("trip", fallback)
        return None

    key = getattr(edge, "trip_id", None)
    if key is not None:
        return ("trip", key)
    fallback = getattr(edge, "route_id", None)
    if fallback is not None:
        return ("route", fallback)
    return None


def _prune_ride_edges_to_first_departure(
    *,
    edges: list,
    current_time: int,
    state_by: str,
    assume_zero_missing: bool,
    max_wait_sec: int | None,
) -> list:
    non_ride_edges: list = []
    best_ride_by_group: dict[tuple[str, object], tuple[int, object]] = {}
    ride_without_group: list = []

    for edge in edges:
        if getattr(edge, "kind", None) not in RIDE_EDGE_KINDS:
            non_ride_edges.append(edge)
            continue

        departure_cursor = _ride_departure_cursor(
            edge=edge,
            current_time=current_time,
            assume_zero_missing=assume_zero_missing,
            max_wait_sec=max_wait_sec,
        )
        if departure_cursor is None:
            continue

        group_key = _state_group_key_for_ride_edge(edge=edge, state_by=state_by)
        if group_key is None:
            ride_without_group.append(edge)
            continue

        existing = best_ride_by_group.get(group_key)
        if existing is None or departure_cursor < existing[0]:
            best_ride_by_group[group_key] = (departure_cursor, edge)

    selected_grouped_ride_edges = [entry[1] for entry in best_ride_by_group.values()]
    return non_ride_edges + ride_without_group + selected_grouped_ride_edges


def td_dijkstra(
    graph: GraphLike,
    start_id: str,
    goal_id: str,
    depart_time_str: str,
    assume_zero_missing: bool = False,
    transfer_penalty_sec: int = 0,
    route_change_penalty_sec: int | None = None,
    time_horizon_sec: int | None = 4 * 3600,
    max_wait_sec: int | None = None,
    state_by: str = "route",
    heuristic_max_speed_mps: float | None = None,
    debug_progress: bool = False,
    debug_progress_every: int = 50000,
) -> PathResult:
    def _normalize_id(value):
        if value is None:
            return None
        if isinstance(value, int) and value == 0:
            return None
        return value

    def _resolve_id(value, kind: str):
        if value is None:
            return None
        if isinstance(value, int):
            if kind == "route" and hasattr(graph, "route_id_for"):
                return graph.route_id_for(value)
            if kind == "trip" and hasattr(graph, "trip_id_for"):
                return graph.trip_id_for(value)
        return value

    depart_time_sec = parse_time_to_seconds(depart_time_str)
    if depart_time_sec is None:
        raise ValueError("Invalid depart_time_str. Expected HH:MM:SS.")
    if route_change_penalty_sec is None:
        route_change_penalty_sec = 0
    if state_by not in {"route", "trip"}:
        raise ValueError("state_by must be 'route' or 'trip'.")
    if max_wait_sec is not None and max_wait_sec <= 0:
        raise ValueError("max_wait_sec must be > 0 when provided.")
    if heuristic_max_speed_mps is not None and heuristic_max_speed_mps <= 0:
        raise ValueError("heuristic_max_speed_mps must be > 0 when provided.")
    if debug_progress_every <= 0:
        raise ValueError("debug_progress_every must be > 0.")
    horizon_end = (
        depart_time_sec + time_horizon_sec if time_horizon_sec is not None else None
    )

    goal_coords = _graph_coordinates_for_node(graph, goal_id)
    heuristic_cache: dict[str, int] = {}

    def _heuristic_seconds(node_id: str) -> int:
        if heuristic_max_speed_mps is None or goal_coords is None:
            return 0
        cached = heuristic_cache.get(node_id)
        if cached is not None:
            return cached
        node_coords = _graph_coordinates_for_node(graph, node_id)
        if node_coords is None:
            heuristic_cache[node_id] = 0
            return 0
        remaining_m = _haversine_distance_m(
            node_coords[0],
            node_coords[1],
            goal_coords[0],
            goal_coords[1],
        )
        heuristic = int(math.ceil(remaining_m / heuristic_max_speed_mps))
        heuristic_cache[node_id] = heuristic
        return heuristic

    start_state = (start_id, None)
    counter = itertools.count()
    heap: list[tuple[int, int, int, str, str | None]] = [
        (
            depart_time_sec + _heuristic_seconds(start_id),
            next(counter),
            depart_time_sec,
            start_id,
            None,
        )
    ]
    dist: dict[tuple[str, str | None], int] = {start_state: depart_time_sec}
    prev: dict[tuple[str, str | None], tuple[tuple[str, str | None], object]] = {}
    goal_state: tuple[str, str | None] | None = None
    best_goal_arrival_sec: int | None = None
    expanded_states = 0
    relaxed_edges = 0

    if debug_progress:
        print(
            "Dijkstra progress: "
            f"searching {start_id} -> {goal_id} from {depart_time_str}."
        )

    while heap:
        (
            estimated_total_sec,
            _order,
            current_time,
            node,
            active_trip_id,
        ) = heapq.heappop(heap)
        state = (node, active_trip_id)
        if current_time != dist.get(state, 0):
            continue
        if (
            best_goal_arrival_sec is not None
            and estimated_total_sec >= best_goal_arrival_sec
        ):
            continue
        expanded_states += 1
        if debug_progress and expanded_states % debug_progress_every == 0:
            current_time_label = seconds_to_time_str(current_time) or str(current_time)
            print(
                "Dijkstra progress: "
                f"expanded {expanded_states} state(s), "
                f"relaxed {relaxed_edges} edge(s), "
                f"frontier={len(heap)}, current={node}@{current_time_label}."
            )
        if node == goal_id:
            if best_goal_arrival_sec is None or current_time < best_goal_arrival_sec:
                best_goal_arrival_sec = current_time
                goal_state = state
            if not heap or (
                best_goal_arrival_sec is not None
                and heap[0][0] >= best_goal_arrival_sec
            ):
                break
            continue

        if horizon_end is not None and current_time > horizon_end:
            continue

        def _relax(
            *,
            next_node: str,
            next_active: str | None,
            new_time: int,
            edge_obj: object,
        ) -> None:
            nonlocal relaxed_edges
            next_state = (next_node, next_active)
            if new_time >= dist.get(next_state, math.inf):
                return
            estimated_arrival = new_time + _heuristic_seconds(next_node)
            if (
                best_goal_arrival_sec is not None
                and estimated_arrival >= best_goal_arrival_sec
            ):
                return
            dist[next_state] = new_time
            prev[next_state] = (state, edge_obj)
            relaxed_edges += 1
            heapq.heappush(
                heap,
                (
                    estimated_arrival,
                    next(counter),
                    new_time,
                    next_node,
                    next_active,
                ),
            )

        use_buckets_override = getattr(graph, "_use_bucket_mode", None)
        if isinstance(use_buckets_override, bool):
            use_buckets = use_buckets_override
        else:
            use_buckets = hasattr(graph, "trip_buckets_from") and hasattr(
                graph, "transfer_edges_from"
            )
        if use_buckets:
            for edge in graph.transfer_edges_from(node):
                new_time: int | None = None
                kind = edge.kind
                weight_sec = edge.weight_sec
                apply_penalty = edge.apply_penalty
                penalty = (
                    transfer_penalty_sec if kind == "transfer" and apply_penalty else 0
                )
                if weight_sec is not None:
                    new_time = current_time + weight_sec + penalty
                elif assume_zero_missing:
                    new_time = current_time + penalty
                if new_time is None:
                    continue
                _relax(
                    next_node=edge.to_stop_id,
                    next_active=None,
                    new_time=new_time,
                    edge_obj=edge,
                )

            for bucket in graph.trip_buckets_from(node):
                if not bucket.dep_secs:
                    continue
                if bucket.last_dep < current_time:
                    continue
                idx = bisect_left(bucket.dep_secs, current_time)
                if idx >= len(bucket.dep_secs):
                    continue
                dep_sec = bucket.dep_secs[idx]
                if horizon_end is not None and dep_sec > horizon_end:
                    continue
                if max_wait_sec is not None and dep_sec - current_time > max_wait_sec:
                    continue
                arr_sec = bucket.arr_secs[idx]
                raw_trip_id = bucket.trip_ids[idx]
                raw_route_id = bucket.route_ids[idx]
                next_active = (
                    _normalize_id(raw_route_id)
                    if state_by == "route"
                    else _normalize_id(raw_trip_id)
                )
                change_penalty = 0
                if (
                    active_trip_id is not None
                    and next_active is not None
                    and next_active != active_trip_id
                ):
                    change_penalty = route_change_penalty_sec
                new_time = arr_sec + change_penalty
                chosen_edge = ChosenEdge(
                    to_stop_id=bucket.to_stop_id,
                    weight_sec=arr_sec - dep_sec,
                    kind="trip",
                    trip_id=_resolve_id(_normalize_id(raw_trip_id), "trip"),
                    route_id=_resolve_id(_normalize_id(raw_route_id), "route"),
                    dep_time=seconds_to_time_str(dep_sec),
                    arr_time=seconds_to_time_str(arr_sec),
                    dep_time_sec=dep_sec,
                    arr_time_sec=arr_sec,
                    transfer_type=None,
                )
                _relax(
                    next_node=bucket.to_stop_id,
                    next_active=next_active,
                    new_time=new_time,
                    edge_obj=chosen_edge,
                )
            continue

        pruned_edges = _prune_ride_edges_to_first_departure(
            edges=list(graph.edges_from(node)),
            current_time=current_time,
            state_by=state_by,
            assume_zero_missing=assume_zero_missing,
            max_wait_sec=max_wait_sec,
        )

        for edge in pruned_edges:
            new_time: int | None = None
            kind = edge.kind
            is_trip_edge = kind in RIDE_EDGE_KINDS
            weight_sec = getattr(edge, "weight_sec", None)
            apply_penalty = getattr(edge, "apply_penalty", True)
            penalty = (
                transfer_penalty_sec if kind == "transfer" and apply_penalty else 0
            )
            change_penalty = 0
            edge_trip_id = getattr(edge, "trip_id", None)
            edge_route_id = getattr(edge, "route_id", None)
            trip_wait_sec = 0
            if (
                is_trip_edge
                and active_trip_id is not None
                and edge_trip_id is not None
                and (
                    (state_by == "trip" and edge_trip_id != active_trip_id)
                    or (state_by == "route" and edge_route_id != active_trip_id)
                )
            ):
                change_penalty = route_change_penalty_sec

            if is_trip_edge:
                dep_sec, arr_sec = _edge_schedule_seconds(edge)
                has_explicit_schedule = dep_sec is not None and arr_sec is not None
                if has_explicit_schedule:
                    wait_sec = dep_sec - current_time
                    if wait_sec < 0 or arr_sec < dep_sec:
                        continue
                    if max_wait_sec is not None and wait_sec > max_wait_sec:
                        continue
                    new_time = arr_sec + penalty + change_penalty
                else:
                    if weight_sec is not None:
                        headway_sec = getattr(edge, "headway_sec", None)
                        if isinstance(headway_sec, int) and headway_sec > 0:
                            trip_wait_sec = headway_sec // 2
                            if (
                                max_wait_sec is not None
                                and trip_wait_sec > max_wait_sec
                            ):
                                continue
                        new_time = (
                            current_time
                            + weight_sec
                            + trip_wait_sec
                            + penalty
                            + change_penalty
                        )
                    elif assume_zero_missing:
                        new_time = current_time + penalty + change_penalty
            else:
                if weight_sec is not None:
                    new_time = (
                        current_time
                        + weight_sec
                        + trip_wait_sec
                        + penalty
                        + change_penalty
                    )
                elif assume_zero_missing:
                    new_time = current_time + penalty + change_penalty

            if new_time is None:
                continue

            next_active = None
            if is_trip_edge:
                next_active = edge_route_id if state_by == "route" else edge_trip_id
            _relax(
                next_node=edge.to_stop_id,
                next_active=next_active,
                new_time=new_time,
                edge_obj=edge,
            )

    if goal_state is None:
        if debug_progress:
            print(
                "Dijkstra progress: "
                f"no path after expanding {expanded_states} state(s)."
            )
        return PathResult(arrival_time_sec=None, stop_path=[], edge_path=[])

    edges: list = []
    stops: list[str] = [goal_state[0]]
    current_state = goal_state
    while current_state != start_state:
        if current_state not in prev:
            break
        prev_state, edge = prev[current_state]
        edges.append(edge)
        stops.append(prev_state[0])
        current_state = prev_state

    stops.reverse()
    edges.reverse()
    if debug_progress:
        arrival_label = seconds_to_time_str(dist[goal_state]) or str(dist[goal_state])
        print(
            "Dijkstra progress: "
            f"done after expanding {expanded_states} state(s); arrival {arrival_label}."
        )
    return PathResult(
        arrival_time_sec=dist[goal_state],
        stop_path=stops,
        edge_path=edges,
    )
