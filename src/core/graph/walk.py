from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000.0
WALK_EDGE_LABEL = "walk"


@dataclass(frozen=True, slots=True)
class WalkEdgeSpec:
    from_stop_id: str
    to_stop_id: str
    distance_m: int
    duration_sec: int


def build_walk_edges(
    *,
    stop_coords: dict[str, tuple[float, float]],
    max_distance_m: int,
    walking_speed_mps: float,
    max_neighbors: int,
    existing_edges: set[tuple[str, str]] | None = None,
) -> list[WalkEdgeSpec]:
    if max_distance_m <= 0 or max_neighbors <= 0:
        return []
    if walking_speed_mps <= 0:
        raise ValueError("walking_speed_mps must be > 0.")
    if len(stop_coords) < 2:
        return []

    projected = _project_stops(stop_coords)
    cell_size_m = float(max_distance_m)
    max_distance_sq = float(max_distance_m * max_distance_m)
    cells: dict[tuple[int, int], list[tuple[str, float, float]]] = defaultdict(list)

    for stop_id, (x, y) in projected.items():
        cell = (int(math.floor(x / cell_size_m)), int(math.floor(y / cell_size_m)))
        cells[cell].append((stop_id, x, y))

    candidates: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for stop_id, (x, y) in projected.items():
        base_cell = (int(math.floor(x / cell_size_m)), int(math.floor(y / cell_size_m)))
        for delta_x in (-1, 0, 1):
            for delta_y in (-1, 0, 1):
                neighbor_cell = (base_cell[0] + delta_x, base_cell[1] + delta_y)
                for other_id, other_x, other_y in cells.get(neighbor_cell, []):
                    if other_id <= stop_id:
                        continue
                    dx = x - other_x
                    dy = y - other_y
                    distance_sq = dx * dx + dy * dy
                    if distance_sq == 0 or distance_sq > max_distance_sq:
                        continue
                    distance_m = int(round(math.sqrt(distance_sq)))
                    candidates[stop_id].append((distance_m, other_id))
                    candidates[other_id].append((distance_m, stop_id))

    edge_specs: list[WalkEdgeSpec] = []
    for from_stop_id, neighbors in candidates.items():
        neighbors.sort(key=lambda value: (value[0], value[1]))
        added = 0
        for distance_m, to_stop_id in neighbors:
            if added >= max_neighbors:
                break
            if (
                existing_edges is not None
                and (from_stop_id, to_stop_id) in existing_edges
            ):
                continue
            duration_sec = max(1, int(round(distance_m / walking_speed_mps)))
            edge_specs.append(
                WalkEdgeSpec(
                    from_stop_id=from_stop_id,
                    to_stop_id=to_stop_id,
                    distance_m=distance_m,
                    duration_sec=duration_sec,
                )
            )
            added += 1
    return edge_specs


def _project_stops(
    stop_coords: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    avg_lat = sum(coords[0] for coords in stop_coords.values()) / len(stop_coords)
    cos_ref = math.cos(math.radians(avg_lat))
    if cos_ref <= 0:
        cos_ref = 1e-8

    projected: dict[str, tuple[float, float]] = {}
    for stop_id, (lat, lon) in stop_coords.items():
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        x = EARTH_RADIUS_M * lon_rad * cos_ref
        y = EARTH_RADIUS_M * lat_rad
        projected[stop_id] = (x, y)
    return projected
