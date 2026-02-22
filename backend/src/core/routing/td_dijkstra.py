from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass
from bisect import bisect_left

from core.routing.types import GraphLike
from core.routing.utils import parse_time_to_seconds, seconds_to_time_str


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


def td_dijkstra(
    graph: GraphLike,
    start_id: str,
    goal_id: str,
    depart_time_str: str,
    assume_zero_missing: bool = False,
    transfer_penalty_sec: int = 300,
    route_change_penalty_sec: int | None = None,
    time_horizon_sec: int | None = 4 * 3600,
    state_by: str = "route",
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
        route_change_penalty_sec = transfer_penalty_sec
    if state_by not in {"route", "trip"}:
        raise ValueError("state_by must be 'route' or 'trip'.")
    horizon_end = (
        depart_time_sec + time_horizon_sec if time_horizon_sec is not None else None
    )

    start_state = (start_id, None)
    counter = itertools.count()
    heap: list[tuple[int, int, str, str | None]] = [
        (depart_time_sec, next(counter), start_id, None)
    ]
    dist: dict[tuple[str, str | None], int] = {start_state: depart_time_sec}
    prev: dict[tuple[str, str | None], tuple[tuple[str, str | None], object]] = {}
    goal_state: tuple[str, str | None] | None = None

    while heap:
        current_time, _order, node, active_trip_id = heapq.heappop(heap)
        state = (node, active_trip_id)
        if current_time != dist.get(state, 0):
            continue
        if node == goal_id:
            goal_state = state
            break

        if horizon_end is not None and current_time > horizon_end:
            continue

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
                next_state = (edge.to_stop_id, None)
                if new_time < dist.get(next_state, math.inf):
                    dist[next_state] = new_time
                    prev[next_state] = (state, edge)
                    heapq.heappush(
                        heap, (new_time, next(counter), edge.to_stop_id, None)
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
                next_state = (bucket.to_stop_id, next_active)
                if new_time < dist.get(next_state, math.inf):
                    dist[next_state] = new_time
                    prev[next_state] = (state, chosen_edge)
                    heapq.heappush(
                        heap,
                        (new_time, next(counter), bucket.to_stop_id, next_active),
                    )
            continue

        for edge in graph.edges_from(node):
            new_time: int | None = None
            kind = edge.kind
            weight_sec = edge.weight_sec
            apply_penalty = edge.apply_penalty
            penalty = (
                transfer_penalty_sec if kind == "transfer" and apply_penalty else 0
            )
            change_penalty = 0
            if (
                kind == "trip"
                and active_trip_id is not None
                and edge.trip_id is not None
                and (
                    (state_by == "trip" and edge.trip_id != active_trip_id)
                    or (state_by == "route" and edge.route_id != active_trip_id)
                )
            ):
                change_penalty = route_change_penalty_sec

            if kind == "trip":
                dep_sec = edge.dep_time_sec
                arr_sec = edge.arr_time_sec
                if dep_sec is None or arr_sec is None:
                    dep_sec = parse_time_to_seconds(edge.dep_time)
                    arr_sec = parse_time_to_seconds(edge.arr_time)
                if dep_sec is not None and arr_sec is not None:
                    if dep_sec >= current_time and arr_sec >= dep_sec:
                        new_time = arr_sec + penalty + change_penalty
            if new_time is None:
                if weight_sec is not None:
                    new_time = current_time + weight_sec + penalty + change_penalty
                elif assume_zero_missing:
                    new_time = current_time + penalty + change_penalty

            if new_time is None:
                continue

            next_active = None
            if kind == "trip":
                next_active = edge.route_id if state_by == "route" else edge.trip_id
            next_state = (edge.to_stop_id, next_active)
            if new_time < dist.get(next_state, math.inf):
                dist[next_state] = new_time
                prev[next_state] = (state, edge)
                heapq.heappush(
                    heap,
                    (new_time, next(counter), edge.to_stop_id, next_active),
                )

    if goal_state is None:
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
    return PathResult(
        arrival_time_sec=dist[goal_state],
        stop_path=stops,
        edge_path=edges,
    )
