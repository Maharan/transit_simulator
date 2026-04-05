from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import cast

from sqlalchemy.orm import Session

from .base import BaseGraph
from .gtfs_support import (
    DEFAULT_WALK_MAX_DISTANCE_M,
    DEFAULT_WALK_MAX_NEIGHBORS,
    DEFAULT_WALK_SPEED_MPS,
    EMPTY_TRIP_BUILD_METADATA,
    TripBuildMetadata,
    edge_timing,
    load_stop_context,
    load_trip_metadata,
    time_to_seconds,
)
from .trip_stop_graph import make_trip_stop_node_id
from core.graph.walk import WALK_EDGE_LABEL, build_walk_edges
from core.gtfs.models import StopTime, Transfer

DEFAULT_SAME_STOP_TRANSFER_SEC = 0

type RouteKey = tuple[str | None, str | None, int | None]
type SegmentKey = tuple[str | None, str | None, int | None, str, str]


@dataclass(frozen=True)
class TripStopAnytimeEdge:
    to_route_stop_id: str
    weight_sec: int | None
    kind: str
    headway_sec: int | None = None
    trip_id: str | None = None
    route_id: str | None = None
    service_id: str | None = None
    direction_id: int | None = None
    transfer_type: int | None = None
    stop_sequence: int | None = None
    apply_penalty: bool = True
    label: str | None = None

    @property
    def to_stop_id(self) -> str:
        return self.to_route_stop_id


class TripStopAnytimeGraph(BaseGraph):
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, str | int | float | None]] = {}
        self.adjacency: dict[str, dict[str, TripStopAnytimeEdge]] = defaultdict(dict)
        self.stop_to_route_stop_ids: dict[str, set[str]] = defaultdict(set)
        self.route_headways: dict[RouteKey, int | None] = {}

    def add_node(
        self,
        route_stop_id: str,
        *,
        stop_id: str,
        trip_id: str,
        route_id: str | None,
        service_id: str | None,
        direction_id: int | None,
        stop_lat: float | None,
        stop_lon: float | None,
    ) -> None:
        self.nodes[route_stop_id] = {
            "stop_id": stop_id,
            "trip_id": trip_id,
            "route_id": route_id,
            "service_id": service_id,
            "direction_id": direction_id,
            "stop_lat": stop_lat,
            "stop_lon": stop_lon,
        }
        self.stop_to_route_stop_ids[stop_id].add(route_stop_id)

    def add_edge(self, from_route_stop_id: str, edge: TripStopAnytimeEdge) -> None:
        outgoing = self.adjacency[from_route_stop_id]
        existing = outgoing.get(edge.to_route_stop_id)
        if existing is None:
            outgoing[edge.to_route_stop_id] = edge
            return
        outgoing[edge.to_route_stop_id] = _preferred_edge(existing, edge)

    def edges_from(self, route_stop_id: str) -> list[TripStopAnytimeEdge]:
        return list(self.adjacency.get(route_stop_id, {}).values())

    def route_stop_ids_for_stop(self, stop_id: str) -> set[str]:
        return set(self.stop_to_route_stop_ids.get(stop_id, set()))


def _effective_cost(edge: TripStopAnytimeEdge) -> int:
    base = edge.weight_sec if edge.weight_sec is not None else 10**9
    if edge.kind != "ride":
        return base
    if edge.headway_sec is None:
        return base
    # In an anytime model, expected wait is approximated as half the headway.
    return base + edge.headway_sec // 2


def _preferred_edge(
    existing: TripStopAnytimeEdge,
    candidate: TripStopAnytimeEdge,
) -> TripStopAnytimeEdge:
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

    if _effective_cost(candidate) < _effective_cost(existing):
        return candidate
    return existing


def _median_int(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def _headway_from_departures(departures: list[int]) -> int | None:
    if len(departures) < 2:
        return None
    ordered = sorted(departures)
    intervals = [
        ordered[idx] - ordered[idx - 1]
        for idx in range(1, len(ordered))
        if ordered[idx] > ordered[idx - 1]
    ]
    if not intervals:
        return None
    return _median_int(intervals)


def _scan_anytime_statistics(
    *,
    session: Session,
    feed_id: str,
    parent_map: dict[str, str],
    trip_meta: dict[str, TripBuildMetadata],
    progress: bool,
    progress_every: int,
) -> tuple[dict[SegmentKey, int], dict[RouteKey, int | None]]:
    segment_durations: dict[SegmentKey, list[int]] = defaultdict(list)
    route_first_departures: dict[RouteKey, list[int]] = defaultdict(list)
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
    current_trip_first_dep_sec: int | None = None
    prev_stop_id: str | None = None
    prev_arrival_time: str | None = None
    prev_departure_time: str | None = None
    scanned_count = 0

    def _flush_trip_departure(trip_id: str | None, first_dep_sec: int | None) -> None:
        if trip_id is None or first_dep_sec is None:
            return
        trip = trip_meta.get(trip_id, EMPTY_TRIP_BUILD_METADATA)
        route_first_departures[
            (trip.route_id, trip.service_id, trip.direction_id)
        ].append(first_dep_sec)

    for (
        trip_id,
        stop_id,
        _stop_sequence,
        arrival_time,
        departure_time,
    ) in stop_time_rows:
        if not trip_id or not stop_id:
            continue
        if trip_id != current_trip_id:
            _flush_trip_departure(current_trip_id, current_trip_first_dep_sec)
            current_trip_id = trip_id
            current_trip_first_dep_sec = time_to_seconds(departure_time or arrival_time)
            prev_stop_id = stop_id
            prev_arrival_time = arrival_time
            prev_departure_time = departure_time
            scanned_count += 1
            continue

        if prev_stop_id:
            from_stop = parent_map.get(prev_stop_id, prev_stop_id)
            to_stop = parent_map.get(stop_id, stop_id)
            if from_stop != to_stop:
                dep_time = prev_departure_time or prev_arrival_time
                arr_time = arrival_time or departure_time
                weight_sec, _dep_sec, _arr_sec = edge_timing(dep_time, arr_time)
                if weight_sec is not None:
                    trip = trip_meta.get(trip_id, EMPTY_TRIP_BUILD_METADATA)
                    key = (
                        trip.route_id,
                        trip.service_id,
                        trip.direction_id,
                        from_stop,
                        to_stop,
                    )
                    segment_durations[key].append(weight_sec)

        prev_stop_id = stop_id
        prev_arrival_time = arrival_time
        prev_departure_time = departure_time
        scanned_count += 1
        if progress and scanned_count % progress_every == 0:
            print(f"Scanned {scanned_count} stop_times rows for anytime statistics...")

    _flush_trip_departure(current_trip_id, current_trip_first_dep_sec)

    segment_weight_by_key = {
        key: _median_int(weights)
        for key, weights in segment_durations.items()
        if _median_int(weights) is not None
    }
    route_headway_by_key = {
        key: _headway_from_departures(departures)
        for key, departures in route_first_departures.items()
    }
    return cast(dict[SegmentKey, int], segment_weight_by_key), route_headway_by_key


def build_trip_stop_anytime_graph_from_gtfs(
    session: Session,
    feed_id: str,
    *,
    connect_same_stop_transfers: bool = True,
    same_stop_transfer_sec: int = DEFAULT_SAME_STOP_TRANSFER_SEC,
    default_headway_sec: int | None = None,
    symmetric_transfers: bool = False,
    enable_walking: bool = True,
    walk_max_distance_m: int = DEFAULT_WALK_MAX_DISTANCE_M,
    walk_speed_mps: float = DEFAULT_WALK_SPEED_MPS,
    walk_max_neighbors: int = DEFAULT_WALK_MAX_NEIGHBORS,
    progress: bool = False,
    progress_every: int = 5000,
) -> TripStopAnytimeGraph:
    if same_stop_transfer_sec < 0:
        raise ValueError("same_stop_transfer_sec must be >= 0.")
    if default_headway_sec is not None and default_headway_sec < 0:
        raise ValueError("default_headway_sec must be >= 0 when provided.")

    stop_context = load_stop_context(session, feed_id)
    parent_map = stop_context.canonical_stop_by_stop_id
    parent_stop_coords = stop_context.coordinates_by_canonical_stop_id
    trip_meta = load_trip_metadata(session, feed_id)
    segment_weight_by_key, route_headway_by_key = _scan_anytime_statistics(
        session=session,
        feed_id=feed_id,
        parent_map=parent_map,
        trip_meta=trip_meta,
        progress=progress,
        progress_every=progress_every,
    )

    graph = TripStopAnytimeGraph()
    graph.route_headways = route_headway_by_key

    def _ensure_node(stop_id: str, trip_id: str) -> str:
        canonical_stop_id = parent_map.get(stop_id, stop_id)
        route_stop_id = make_trip_stop_node_id(canonical_stop_id, trip_id)
        if route_stop_id in graph.nodes:
            return route_stop_id
        stop_lat, stop_lon = parent_stop_coords.get(canonical_stop_id, (None, None))
        trip = trip_meta.get(trip_id, EMPTY_TRIP_BUILD_METADATA)
        graph.add_node(
            route_stop_id,
            stop_id=canonical_stop_id,
            trip_id=trip_id,
            route_id=trip.route_id,
            service_id=trip.service_id,
            direction_id=trip.direction_id,
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
                from_stop = parent_map.get(prev_stop_id, prev_stop_id)
                to_stop = parent_map.get(stop_id, stop_id)
                trip = trip_meta.get(trip_id, EMPTY_TRIP_BUILD_METADATA)
                segment_key = (
                    trip.route_id,
                    trip.service_id,
                    trip.direction_id,
                    from_stop,
                    to_stop,
                )
                route_key = (trip.route_id, trip.service_id, trip.direction_id)
                dep_time = prev_departure_time or prev_arrival_time
                arr_time = arrival_time or departure_time
                observed_weight, _dep_sec, _arr_sec = edge_timing(dep_time, arr_time)
                anytime_weight = segment_weight_by_key.get(segment_key, observed_weight)
                computed_headway_sec = route_headway_by_key.get(route_key)
                headway_sec = (
                    computed_headway_sec
                    if computed_headway_sec is not None
                    else default_headway_sec
                )
                graph.add_edge(
                    from_node,
                    TripStopAnytimeEdge(
                        to_route_stop_id=to_node,
                        weight_sec=anytime_weight,
                        kind="ride",
                        headway_sec=headway_sec,
                        trip_id=trip_id,
                        route_id=trip.route_id,
                        service_id=trip.service_id,
                        direction_id=trip.direction_id,
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
            print(f"Scanned {stop_time_count} stop_times rows for anytime graph...")
    if progress:
        print(f"Scanned {stop_time_count} stop_times rows for anytime graph total.")
        print(f"Built {ride_edge_count} ride edges for anytime graph.")

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
                        TripStopAnytimeEdge(
                            to_route_stop_id=to_node,
                            weight_sec=same_stop_transfer_sec,
                            kind="transfer",
                            transfer_type=2,
                        ),
                    )
                    same_stop_transfer_count += 1
        if progress:
            print(
                "Added "
                f"{same_stop_transfer_count} same-stop transfer edges in anytime graph."
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
    for from_stop_id, to_stop_id, min_transfer_time, transfer_type in transfer_rows:
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
                    TripStopAnytimeEdge(
                        to_route_stop_id=to_node,
                        weight_sec=min_transfer_time,
                        kind="transfer",
                        transfer_type=transfer_type,
                    ),
                )
                explicit_transfer_count += 1
        if symmetric_transfers:
            explicit_stop_pairs.add((to_stop, from_stop))
            for to_node in to_nodes:
                for from_node in from_nodes:
                    graph.add_edge(
                        to_node,
                        TripStopAnytimeEdge(
                            to_route_stop_id=from_node,
                            weight_sec=min_transfer_time,
                            kind="transfer",
                            transfer_type=transfer_type,
                        ),
                    )
                    explicit_transfer_count += 1
    if progress:
        print(
            "Added "
            f"{explicit_transfer_count} inter-stop transfer edges in anytime graph."
        )

    if enable_walking:
        walk_specs = build_walk_edges(
            stop_coords=parent_stop_coords,
            max_distance_m=walk_max_distance_m,
            walking_speed_mps=walk_speed_mps,
            max_neighbors=walk_max_neighbors,
            existing_edges=explicit_stop_pairs,
        )
        walk_edge_count = 0
        for spec in walk_specs:
            from_nodes = graph.route_stop_ids_for_stop(spec.from_stop_id)
            to_nodes = graph.route_stop_ids_for_stop(spec.to_stop_id)
            for from_node in from_nodes:
                for to_node in to_nodes:
                    graph.add_edge(
                        from_node,
                        TripStopAnytimeEdge(
                            to_route_stop_id=to_node,
                            weight_sec=spec.duration_sec,
                            kind="transfer",
                            transfer_type=None,
                            apply_penalty=False,
                            label=WALK_EDGE_LABEL,
                        ),
                    )
                    walk_edge_count += 1
        if progress:
            print(f"Added {walk_edge_count} walking edges in anytime graph.")

    return graph
