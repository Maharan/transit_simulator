from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass

from routing.types import GraphLike
from routing.utils import parse_time_to_seconds


@dataclass(frozen=True)
class PathResult:
    arrival_time_sec: int | None
    stop_path: list[str]
    edge_path: list


def td_dijkstra(
    graph: GraphLike,
    start_id: str,
    goal_id: str,
    depart_time_str: str,
    assume_zero_missing: bool = False,
    transfer_penalty_sec: int = 300,
    route_change_penalty_sec: int | None = None,
) -> PathResult:
    depart_time_sec = parse_time_to_seconds(depart_time_str)
    if depart_time_sec is None:
        raise ValueError("Invalid depart_time_str. Expected HH:MM:SS.")
    if route_change_penalty_sec is None:
        route_change_penalty_sec = transfer_penalty_sec

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

        for edge in graph.edges_from(node):
            new_time: int | None = None
            apply_penalty = getattr(edge, "apply_penalty", True)
            penalty = (
                transfer_penalty_sec
                if getattr(edge, "kind", None) == "transfer" and apply_penalty
                else 0
            )
            change_penalty = 0
            if (
                getattr(edge, "kind", None) == "trip"
                and active_trip_id is not None
                and getattr(edge, "trip_id", None) is not None
                and getattr(edge, "trip_id") != active_trip_id
            ):
                change_penalty = route_change_penalty_sec

            dep_sec = parse_time_to_seconds(getattr(edge, "dep_time", None))
            arr_sec = parse_time_to_seconds(getattr(edge, "arr_time", None))
            if dep_sec is not None and arr_sec is not None:
                if dep_sec >= current_time and arr_sec >= dep_sec:
                    new_time = arr_sec + penalty + change_penalty
            elif edge.weight_sec is not None:
                new_time = current_time + edge.weight_sec + penalty + change_penalty
            elif assume_zero_missing:
                new_time = current_time + penalty + change_penalty

            if new_time is None:
                continue

            next_trip_id = (
                getattr(edge, "trip_id", None)
                if getattr(edge, "kind", None) == "trip"
                else None
            )
            next_state = (edge.to_stop_id, next_trip_id)
            if new_time < dist.get(next_state, math.inf):
                dist[next_state] = new_time
                prev[next_state] = (state, edge)
                heapq.heappush(
                    heap,
                    (new_time, next(counter), edge.to_stop_id, next_trip_id),
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
