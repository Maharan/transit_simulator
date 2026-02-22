from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import cast

from sqlalchemy.orm import Session

from .base import BaseGraph
from .multi_edge_graph import (
    DEFAULT_WALK_MAX_DISTANCE_M,
    DEFAULT_WALK_MAX_NEIGHBORS,
    DEFAULT_WALK_SPEED_MPS,
    _edge_timing,
)
from core.graph.walk import WALK_EDGE_LABEL, build_walk_edges
from core.gtfs.models import Stop, StopTime, Transfer, Trip
from core.routing.utils import seconds_to_time_str

TRIP_STOP_NODE_SEPARATOR = "::"
DEFAULT_SAME_STOP_TRANSFER_SEC = 0


def make_trip_stop_node_id(stop_id: str, trip_id: str) -> str:
    return f"{stop_id}{TRIP_STOP_NODE_SEPARATOR}{trip_id}"


def split_trip_stop_node_id(node_id: str) -> tuple[str, str]:
    stop_id, separator, trip_id = node_id.partition(TRIP_STOP_NODE_SEPARATOR)
    if not separator or not stop_id or not trip_id:
        raise ValueError(
            "Trip-stop node ids must use the '<stop_id>::<trip_id>' format."
        )
    return stop_id, trip_id


@dataclass(frozen=True)
class TripStopEdge:
    to_route_stop_id: str
    weight_sec: int | None
    kind: str
    trip_id: str | None = None
    route_id: str | None = None
    dep_time_sec: int | None = None
    arr_time_sec: int | None = None
    transfer_type: int | None = None
    stop_sequence: int | None = None
    apply_penalty: bool = True
    label: str | None = None

    @property
    def to_stop_id(self) -> str:
        return self.to_route_stop_id

    @property
    def dep_time(self) -> str | None:
        if self.dep_time_sec is None:
            return None
        return seconds_to_time_str(self.dep_time_sec)

    @property
    def arr_time(self) -> str | None:
        if self.arr_time_sec is None:
            return None
        return seconds_to_time_str(self.arr_time_sec)


class TripStopGraph(BaseGraph):
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, str | float | None]] = {}
        self.adjacency: dict[str, dict[str, TripStopEdge]] = defaultdict(dict)
        self.stop_to_route_stop_ids: dict[str, set[str]] = defaultdict(set)

    def add_node(
        self,
        route_stop_id: str,
        *,
        stop_id: str,
        trip_id: str,
        route_id: str | None,
        service_id: str | None,
        stop_lat: float | None,
        stop_lon: float | None,
    ) -> None:
        self.nodes[route_stop_id] = {
            "stop_id": stop_id,
            "trip_id": trip_id,
            "route_id": route_id,
            "service_id": service_id,
            "stop_lat": stop_lat,
            "stop_lon": stop_lon,
        }
        self.stop_to_route_stop_ids[stop_id].add(route_stop_id)

    def add_edge(self, from_route_stop_id: str, edge: TripStopEdge) -> None:
        outgoing = self.adjacency[from_route_stop_id]
        existing = outgoing.get(edge.to_route_stop_id)
        if existing is None:
            outgoing[edge.to_route_stop_id] = edge
            return
        outgoing[edge.to_route_stop_id] = _preferred_edge(existing, edge)

    def edges_from(self, route_stop_id: str) -> list[TripStopEdge]:
        return list(self.adjacency.get(route_stop_id, {}).values())

    def route_stop_ids_for_stop(self, stop_id: str) -> set[str]:
        return set(self.stop_to_route_stop_ids.get(stop_id, set()))


def _preferred_edge(existing: TripStopEdge, candidate: TripStopEdge) -> TripStopEdge:
    # Keep scheduled ride edges over transfer/walk shortcuts for the same pair.
    if existing.kind == "ride" and candidate.kind != "ride":
        return existing
    if candidate.kind == "ride" and existing.kind != "ride":
        return candidate

    existing_is_walk = existing.label == WALK_EDGE_LABEL
    candidate_is_walk = candidate.label == WALK_EDGE_LABEL
    if existing_is_walk and not candidate_is_walk:
        return candidate
    if candidate_is_walk and not existing_is_walk:
        return existing

    existing_weight = existing.weight_sec if existing.weight_sec is not None else 10**9
    candidate_weight = (
        candidate.weight_sec if candidate.weight_sec is not None else 10**9
    )
    if candidate_weight < existing_weight:
        return candidate
    return existing


def build_trip_stop_graph_from_gtfs(
    session: Session,
    feed_id: str,
    *,
    connect_same_stop_transfers: bool = True,
    same_stop_transfer_sec: int = DEFAULT_SAME_STOP_TRANSFER_SEC,
    symmetric_transfers: bool = False,
    enable_walking: bool = True,
    walk_max_distance_m: int = DEFAULT_WALK_MAX_DISTANCE_M,
    walk_speed_mps: float = DEFAULT_WALK_SPEED_MPS,
    walk_max_neighbors: int = DEFAULT_WALK_MAX_NEIGHBORS,
    progress: bool = False,
    progress_every: int = 5000,
) -> TripStopGraph:
    if same_stop_transfer_sec < 0:
        raise ValueError("same_stop_transfer_sec must be >= 0.")

    graph = TripStopGraph()
    parent_map: dict[str, str] = {}
    parent_stop_coords: dict[str, tuple[float, float]] = {}

    stops = (
        session.query(Stop.stop_id, Stop.parent_station, Stop.stop_lat, Stop.stop_lon)
        .filter(Stop.feed_id == feed_id)
        .yield_per(5000)
    )
    stop_count = 0
    for stop_id, parent_station, stop_lat, stop_lon in stops:
        if not stop_id:
            continue
        node_stop_id = parent_station or stop_id
        parent_map[stop_id] = node_stop_id
        if stop_lat is not None and stop_lon is not None:
            parent_stop_coords.setdefault(
                node_stop_id, (float(stop_lat), float(stop_lon))
            )
        stop_count += 1
        if progress and stop_count % progress_every == 0:
            print(f"Loaded {stop_count} stops for trip-stop graph...")
    if progress:
        print(f"Loaded {stop_count} stops for trip-stop graph total.")

    trip_meta: dict[str, tuple[str | None, str | None]] = {}
    trip_rows = (
        session.query(Trip.trip_id, Trip.route_id, Trip.service_id)
        .filter(Trip.feed_id == feed_id)
        .yield_per(5000)
    )
    for trip_id, route_id, service_id in trip_rows:
        if not trip_id:
            continue
        trip_meta[trip_id] = (route_id, service_id)

    def _ensure_node(stop_id: str, trip_id: str) -> str:
        canonical_stop_id = parent_map.get(stop_id, stop_id)
        route_stop_id = make_trip_stop_node_id(canonical_stop_id, trip_id)
        if route_stop_id in graph.nodes:
            return route_stop_id
        stop_lat, stop_lon = parent_stop_coords.get(canonical_stop_id, (None, None))
        route_id, service_id = trip_meta.get(trip_id, (None, None))
        graph.add_node(
            route_stop_id,
            stop_id=canonical_stop_id,
            trip_id=trip_id,
            route_id=route_id,
            service_id=service_id,
            stop_lat=cast(float | None, stop_lat),
            stop_lon=cast(float | None, stop_lon),
        )
        return route_stop_id

    stop_time_rows = (
        session.query(
            StopTime.trip_id,
            StopTime.stop_id,
            StopTime.stop_sequence,
            StopTime.arrival_time,
            StopTime.departure_time,
        )
        .filter(StopTime.feed_id == feed_id)
        .order_by(StopTime.trip_id, StopTime.stop_sequence)
        .yield_per(5000)
    )
    current_trip_id: str | None = None
    prev_stop_id: str | None = None
    prev_stop_sequence: int | None = None
    prev_arrival_time: str | None = None
    prev_departure_time: str | None = None
    stop_time_count = 0
    ride_edge_count = 0

    for trip_id, stop_id, stop_sequence, arrival_time, departure_time in stop_time_rows:
        if not trip_id or not stop_id:
            continue
        _ensure_node(stop_id, trip_id)
        if trip_id != current_trip_id:
            current_trip_id = trip_id
            prev_stop_id = stop_id
            prev_stop_sequence = stop_sequence
            prev_arrival_time = arrival_time
            prev_departure_time = departure_time
            stop_time_count += 1
            continue

        if prev_stop_id:
            from_node = _ensure_node(prev_stop_id, trip_id)
            to_node = _ensure_node(stop_id, trip_id)
            if from_node != to_node:
                dep_time = prev_departure_time or prev_arrival_time
                arr_time = arrival_time or departure_time
                weight_sec, dep_sec, arr_sec = _edge_timing(dep_time, arr_time)
                route_id, _service_id = trip_meta.get(trip_id, (None, None))
                graph.add_edge(
                    from_node,
                    TripStopEdge(
                        to_route_stop_id=to_node,
                        weight_sec=weight_sec,
                        kind="ride",
                        trip_id=trip_id,
                        route_id=route_id,
                        dep_time_sec=dep_sec,
                        arr_time_sec=arr_sec,
                        stop_sequence=prev_stop_sequence,
                    ),
                )
                ride_edge_count += 1

        prev_stop_id = stop_id
        prev_stop_sequence = stop_sequence
        prev_arrival_time = arrival_time
        prev_departure_time = departure_time
        stop_time_count += 1
        if progress and stop_time_count % progress_every == 0:
            print(f"Scanned {stop_time_count} stop_times rows for trip-stop graph...")
    if progress:
        print(f"Scanned {stop_time_count} stop_times rows for trip-stop graph total.")
        print(f"Built {ride_edge_count} ride edges.")

    same_stop_transfer_count = 0
    if connect_same_stop_transfers:
        for route_stop_ids in graph.stop_to_route_stop_ids.values():
            if len(route_stop_ids) < 2:
                continue
            route_stop_id_list = sorted(route_stop_ids)
            for from_node in route_stop_id_list:
                for to_node in route_stop_id_list:
                    if from_node == to_node:
                        continue
                    graph.add_edge(
                        from_node,
                        TripStopEdge(
                            to_route_stop_id=to_node,
                            weight_sec=same_stop_transfer_sec,
                            kind="transfer",
                            transfer_type=2,
                        ),
                    )
                    same_stop_transfer_count += 1
                    if progress and same_stop_transfer_count % progress_every == 0:
                        print(
                            "Added "
                            f"{same_stop_transfer_count} same-stop transfer edges so far..."
                        )
        if progress:
            print(
                "Added "
                f"{same_stop_transfer_count} same-stop transfer edges in trip-stop graph."
            )

    transfer_rows = (
        session.query(
            Transfer.from_stop_id,
            Transfer.to_stop_id,
            Transfer.min_transfer_time,
            Transfer.transfer_type,
        )
        .filter(Transfer.feed_id == feed_id)
        .yield_per(5000)
    )
    explicit_stop_pairs: set[tuple[str, str]] = set()
    explicit_transfer_count = 0
    explicit_transfer_rows = 0
    for from_stop_id, to_stop_id, min_transfer_time, transfer_type in transfer_rows:
        explicit_transfer_rows += 1
        if progress and explicit_transfer_rows % progress_every == 0:
            print(
                "Scanned "
                f"{explicit_transfer_rows} GTFS transfer row(s) for trip-stop graph..."
            )
        if not from_stop_id or not to_stop_id:
            continue
        from_stop = parent_map.get(from_stop_id, from_stop_id)
        to_stop = parent_map.get(to_stop_id, to_stop_id)
        if from_stop == to_stop:
            continue
        explicit_stop_pairs.add((from_stop, to_stop))
        from_nodes = graph.route_stop_ids_for_stop(from_stop)
        to_nodes = graph.route_stop_ids_for_stop(to_stop)
        for from_node in from_nodes:
            for to_node in to_nodes:
                graph.add_edge(
                    from_node,
                    TripStopEdge(
                        to_route_stop_id=to_node,
                        weight_sec=min_transfer_time,
                        kind="transfer",
                        transfer_type=transfer_type,
                    ),
                )
                explicit_transfer_count += 1
                if progress and explicit_transfer_count % progress_every == 0:
                    print(
                        "Added "
                        f"{explicit_transfer_count} inter-stop transfer edges so far..."
                    )
        if symmetric_transfers:
            explicit_stop_pairs.add((to_stop, from_stop))
            for to_node in to_nodes:
                for from_node in from_nodes:
                    graph.add_edge(
                        to_node,
                        TripStopEdge(
                            to_route_stop_id=from_node,
                            weight_sec=min_transfer_time,
                            kind="transfer",
                            transfer_type=transfer_type,
                        ),
                    )
                    explicit_transfer_count += 1
                    if progress and explicit_transfer_count % progress_every == 0:
                        print(
                            "Added "
                            f"{explicit_transfer_count} inter-stop transfer edges so far..."
                        )
    if progress:
        print(
            "Added "
            f"{explicit_transfer_count} inter-stop transfer edges in trip-stop graph."
        )

    if enable_walking:
        if progress:
            print("Building walking stop-pair specs for trip-stop graph...")
        walk_specs = build_walk_edges(
            stop_coords=parent_stop_coords,
            max_distance_m=walk_max_distance_m,
            walking_speed_mps=walk_speed_mps,
            max_neighbors=walk_max_neighbors,
            existing_edges=explicit_stop_pairs,
        )
        if progress:
            print(
                "Computed "
                f"{len(walk_specs)} walking stop-pair spec(s); expanding to trip-stop nodes..."
            )
        walk_edge_count = 0
        for spec in walk_specs:
            from_nodes = graph.route_stop_ids_for_stop(spec.from_stop_id)
            to_nodes = graph.route_stop_ids_for_stop(spec.to_stop_id)
            for from_node in from_nodes:
                for to_node in to_nodes:
                    graph.add_edge(
                        from_node,
                        TripStopEdge(
                            to_route_stop_id=to_node,
                            weight_sec=spec.duration_sec,
                            kind="transfer",
                            transfer_type=None,
                            apply_penalty=False,
                            label=WALK_EDGE_LABEL,
                        ),
                    )
                    walk_edge_count += 1
                    if progress and walk_edge_count % progress_every == 0:
                        print(
                            f"Added {walk_edge_count} walking edges so far in trip-stop graph..."
                        )
        if progress:
            print(f"Added {walk_edge_count} walking edges in trip-stop graph.")

    return graph
