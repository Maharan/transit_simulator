from __future__ import annotations

import heapq
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PathResult:
    arrival_time_sec: int | None
    stop_path: list[str]
    edge_path: list


def parse_time_to_seconds(time_str: str | None) -> int | None:
    if not time_str:
        return None
    parts = time_str.split(":")
    if len(parts) != 3:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except ValueError:
        return None
    if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
        return None
    return hours * 3600 + minutes * 60 + seconds


def td_dijkstra(
    graph,
    start_id: str,
    goal_id: str,
    depart_time_str: str,
    assume_zero_missing: bool = False,
    transfer_penalty_sec: int = 300,
) -> PathResult:
    depart_time_sec = parse_time_to_seconds(depart_time_str)
    if depart_time_sec is None:
        raise ValueError("Invalid depart_time_str. Expected HH:MM:SS.")

    heap: list[tuple[int, str]] = [(depart_time_sec, start_id)]
    dist: dict[str, int] = {start_id: depart_time_sec}
    prev: dict[str, tuple[str, object]] = {}

    while heap:
        current_time, node = heapq.heappop(heap)
        if node == goal_id:
            break
        if current_time != dist.get(node, 0):
            continue

        for edge in graph.edges_from(node):
            new_time: int | None = None
            apply_penalty = getattr(edge, "apply_penalty", True)
            penalty = (
                transfer_penalty_sec
                if getattr(edge, "kind", None) == "transfer" and apply_penalty
                else 0
            )

            dep_sec = parse_time_to_seconds(getattr(edge, "dep_time", None))
            arr_sec = parse_time_to_seconds(getattr(edge, "arr_time", None))
            if dep_sec is not None and arr_sec is not None:
                if dep_sec >= current_time and arr_sec >= dep_sec:
                    new_time = arr_sec + penalty
            elif edge.weight_sec is not None:
                new_time = current_time + edge.weight_sec + penalty
            elif assume_zero_missing:
                new_time = current_time + penalty

            if new_time is None:
                continue

            if new_time < dist.get(edge.to_stop_id, math.inf):
                dist[edge.to_stop_id] = new_time
                prev[edge.to_stop_id] = (node, edge)
                heapq.heappush(heap, (new_time, edge.to_stop_id))

    if goal_id not in dist:
        return PathResult(arrival_time_sec=None, stop_path=[], edge_path=[])

    edges: list = []
    stops: list[str] = [goal_id]
    current = goal_id
    while current != start_id:
        if current not in prev:
            break
        prev_node, edge = prev[current]
        edges.append(edge)
        stops.append(prev_node)
        current = prev_node

    stops.reverse()
    edges.reverse()
    return PathResult(arrival_time_sec=dist[goal_id], stop_path=stops, edge_path=edges)
