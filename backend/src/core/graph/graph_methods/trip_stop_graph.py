from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
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
DEFAULT_TRANSFER_EDGE_PENALTY_SEC = 30
SAME_STOP_TRANSFER_HUB_PREFIX = "__same_stop_transfer__"

type TransferAdjacencyTuple = tuple[str, int | None, int | None, bool, str | None]
type RideScheduleTuple = tuple[int, int, str | None, str | None]
type PatternKey = tuple[str | None, int | None, tuple[str, ...]]


def make_trip_stop_node_id(stop_id: str, trip_id: str) -> str:
    return f"{stop_id}{TRIP_STOP_NODE_SEPARATOR}{trip_id}"


def make_same_stop_transfer_hub_node_id(stop_id: str) -> str:
    return f"{SAME_STOP_TRANSFER_HUB_PREFIX}{stop_id}"


def split_trip_stop_node_id(node_id: str) -> tuple[str, str]:
    stop_id, separator, trip_id = node_id.partition(TRIP_STOP_NODE_SEPARATOR)
    if not separator or not stop_id or not trip_id:
        raise ValueError(
            "Trip-stop node ids must use the '<stop_id>::<trip_id>' format."
        )
    return stop_id, trip_id


@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True)
class TripStopTripBucket:
    to_stop_id: str
    dep_secs: list[int]
    arr_secs: list[int]
    trip_ids: list[str | None]
    route_ids: list[str | None]
    last_dep: int


class TripStopGraph(BaseGraph):
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, object | None]] = {}
        self.adjacency: dict[str, list[TransferAdjacencyTuple]] = defaultdict(list)
        self._adjacency_index_by_to: dict[str, dict[str, int]] = defaultdict(dict)
        self._ride_entries: dict[tuple[str, str], list[RideScheduleTuple]] = (
            defaultdict(list)
        )
        self._trip_buckets_dirty = False
        self.trip_buckets: dict[str, list[TripStopTripBucket]] = defaultdict(list)
        self._fallback_ride_edges: dict[str, list[TripStopEdge]] = defaultdict(list)
        self.stop_to_route_stop_ids: dict[str, set[str]] = defaultdict(set)
        self.same_stop_transfer_hub_ids: dict[str, str] = {}
        self.trip_to_pattern_id: dict[str, str] = {}
        self._use_bucket_mode = True

    def add_node(
        self,
        route_stop_id: str,
        *,
        stop_id: str,
        pattern_id: str | None,
        route_id: str | None,
        service_id: str | None,
        direction_id: int | None,
        stop_lat: float | None,
        stop_lon: float | None,
        include_in_stop_index: bool = True,
    ) -> None:
        self.nodes[route_stop_id] = {
            "stop_id": stop_id,
            "pattern_id": pattern_id,
            "route_id": route_id,
            "service_id": service_id,
            "direction_id": direction_id,
            "stop_lat": stop_lat,
            "stop_lon": stop_lon,
        }
        if include_in_stop_index:
            self.stop_to_route_stop_ids[stop_id].add(route_stop_id)

    def add_edge(self, from_route_stop_id: str, edge: TripStopEdge) -> None:
        if edge.kind in {"ride", "trip"}:
            if edge.dep_time_sec is not None and edge.arr_time_sec is not None:
                self.add_ride_departure(
                    from_route_stop_id,
                    to_route_stop_id=edge.to_route_stop_id,
                    dep_time_sec=edge.dep_time_sec,
                    arr_time_sec=edge.arr_time_sec,
                    trip_id=edge.trip_id,
                    route_id=edge.route_id,
                )
                return
            self._fallback_ride_edges[from_route_stop_id].append(edge)
            self._use_bucket_mode = False
            return

        self.add_transfer_edge(
            from_route_stop_id,
            to_route_stop_id=edge.to_route_stop_id,
            weight_sec=edge.weight_sec,
            transfer_type=edge.transfer_type,
            apply_penalty=edge.apply_penalty,
            label=edge.label,
        )

    def add_transfer_edge(
        self,
        from_route_stop_id: str,
        *,
        to_route_stop_id: str,
        weight_sec: int | None,
        transfer_type: int | None,
        apply_penalty: bool = True,
        label: str | None = None,
    ) -> None:
        candidate: TransferAdjacencyTuple = (
            to_route_stop_id,
            weight_sec,
            transfer_type,
            apply_penalty,
            label,
        )
        index_by_to = self._adjacency_index_by_to[from_route_stop_id]
        existing_index = index_by_to.get(to_route_stop_id)
        if existing_index is None:
            index_by_to[to_route_stop_id] = len(self.adjacency[from_route_stop_id])
            self.adjacency[from_route_stop_id].append(candidate)
            return
        existing = self.adjacency[from_route_stop_id][existing_index]
        self.adjacency[from_route_stop_id][existing_index] = _preferred_transfer_edge(
            existing,
            candidate,
        )

    def add_ride_departure(
        self,
        from_route_stop_id: str,
        *,
        to_route_stop_id: str,
        dep_time_sec: int,
        arr_time_sec: int,
        trip_id: str | None,
        route_id: str | None,
    ) -> None:
        if arr_time_sec < dep_time_sec:
            return
        self._ride_entries[(from_route_stop_id, to_route_stop_id)].append(
            (dep_time_sec, arr_time_sec, trip_id, route_id)
        )
        self._trip_buckets_dirty = True

    def finalize(self) -> None:
        self._ensure_trip_buckets()

    def edges_from(self, route_stop_id: str) -> list[TripStopEdge]:
        transfer_edges = self.transfer_edges_from(route_stop_id)
        self._ensure_trip_buckets()
        buckets = self.trip_buckets.get(route_stop_id, [])
        if self._use_bucket_mode:
            edges = list(transfer_edges)
            for bucket in buckets:
                if not bucket.dep_secs:
                    continue
                edges.append(
                    TripStopEdge(
                        to_route_stop_id=bucket.to_stop_id,
                        weight_sec=bucket.arr_secs[0] - bucket.dep_secs[0],
                        kind="ride",
                        trip_id=bucket.trip_ids[0],
                        route_id=bucket.route_ids[0],
                        dep_time_sec=bucket.dep_secs[0],
                        arr_time_sec=bucket.arr_secs[0],
                    )
                )
            return edges

        edges = list(transfer_edges)
        for bucket in buckets:
            for dep_sec, arr_sec, trip_id, route_id in zip(
                bucket.dep_secs,
                bucket.arr_secs,
                bucket.trip_ids,
                bucket.route_ids,
                strict=False,
            ):
                edges.append(
                    TripStopEdge(
                        to_route_stop_id=bucket.to_stop_id,
                        weight_sec=arr_sec - dep_sec,
                        kind="ride",
                        trip_id=trip_id,
                        route_id=route_id,
                        dep_time_sec=dep_sec,
                        arr_time_sec=arr_sec,
                    )
                )
        edges.extend(self._fallback_ride_edges.get(route_stop_id, []))
        return edges

    def transfer_edges_from(self, route_stop_id: str) -> list[TripStopEdge]:
        edges: list[TripStopEdge] = []
        for (
            to_route_stop_id,
            weight_sec,
            transfer_type,
            apply_penalty,
            label,
        ) in self.adjacency.get(route_stop_id, []):
            edges.append(
                TripStopEdge(
                    to_route_stop_id=to_route_stop_id,
                    weight_sec=weight_sec,
                    kind="transfer",
                    transfer_type=transfer_type,
                    apply_penalty=apply_penalty,
                    label=label,
                )
            )
        return edges

    def trip_buckets_from(self, route_stop_id: str) -> list[TripStopTripBucket]:
        self._ensure_trip_buckets()
        return self.trip_buckets.get(route_stop_id, [])

    def route_stop_ids_for_stop(self, stop_id: str) -> set[str]:
        return set(self.stop_to_route_stop_ids.get(stop_id, set()))

    def ensure_same_stop_transfer_hub(
        self,
        *,
        stop_id: str,
        stop_lat: float | None,
        stop_lon: float | None,
    ) -> str:
        existing = self.same_stop_transfer_hub_ids.get(stop_id)
        if existing is not None:
            return existing
        hub_node_id = make_same_stop_transfer_hub_node_id(stop_id)
        self.same_stop_transfer_hub_ids[stop_id] = hub_node_id
        self.add_node(
            hub_node_id,
            stop_id=stop_id,
            pattern_id=None,
            route_id=None,
            service_id=None,
            direction_id=None,
            stop_lat=stop_lat,
            stop_lon=stop_lon,
            include_in_stop_index=False,
        )
        return hub_node_id

    def coordinates_for_node(self, node_id: str) -> tuple[float, float] | None:
        node_data = self.nodes.get(node_id)
        if not isinstance(node_data, dict):
            return None
        lat = node_data.get("stop_lat")
        lon = node_data.get("stop_lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return None
        return float(lat), float(lon)

    def _ensure_trip_buckets(self) -> None:
        if not self._trip_buckets_dirty:
            return
        self.trip_buckets.clear()
        for (
            from_route_stop_id,
            to_route_stop_id,
        ), entries in self._ride_entries.items():
            if not entries:
                continue
            ordered_entries = sorted(entries, key=lambda entry: entry[0])
            dep_secs = [entry[0] for entry in ordered_entries]
            arr_secs = [entry[1] for entry in ordered_entries]
            trip_ids = [entry[2] for entry in ordered_entries]
            route_ids = [entry[3] for entry in ordered_entries]
            self.trip_buckets[from_route_stop_id].append(
                TripStopTripBucket(
                    to_stop_id=to_route_stop_id,
                    dep_secs=dep_secs,
                    arr_secs=arr_secs,
                    trip_ids=trip_ids,
                    route_ids=route_ids,
                    last_dep=dep_secs[-1],
                )
            )
        self._trip_buckets_dirty = False


def _preferred_transfer_edge(
    existing: TransferAdjacencyTuple,
    candidate: TransferAdjacencyTuple,
) -> TransferAdjacencyTuple:
    existing_is_walk = existing[4] == WALK_EDGE_LABEL
    candidate_is_walk = candidate[4] == WALK_EDGE_LABEL
    if existing_is_walk and not candidate_is_walk:
        return candidate
    if candidate_is_walk and not existing_is_walk:
        return existing
    existing_weight = existing[1] if existing[1] is not None else 10**9
    candidate_weight = candidate[1] if candidate[1] is not None else 10**9
    if candidate_weight < existing_weight:
        return candidate
    return existing


def _with_transfer_edge_penalty(
    weight_sec: int | None,
    transfer_edge_penalty_sec: int,
) -> int:
    return max(0, int(weight_sec or 0)) + transfer_edge_penalty_sec


def _pattern_id_from_key(pattern_key: PatternKey) -> str:
    route_id, direction_id, stop_sequence = pattern_key
    key_payload = (
        f"{route_id or ''}|"
        f"{'' if direction_id is None else direction_id}|"
        f"{','.join(stop_sequence)}"
    )
    digest = hashlib.md5(key_payload.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"pattern_{digest[:12]}"


def _build_trip_pattern_map(
    *,
    session: Session,
    feed_id: str,
    parent_map: dict[str, str],
    trip_meta: dict[str, tuple[str | None, str | None, int | None]],
    progress: bool,
    progress_every: int,
) -> dict[str, str]:
    trip_to_pattern_id: dict[str, str] = {}
    pattern_key_to_id: dict[PatternKey, str] = {}
    stop_time_rows = (
        session.query(
            StopTime.trip_id,
            StopTime.stop_id,
            StopTime.stop_sequence,
        )
        .filter(StopTime.feed_id == feed_id)
        .order_by(StopTime.trip_id, StopTime.stop_sequence)
        .yield_per(5000)
    )

    current_trip_id: str | None = None
    current_trip_stop_sequence: list[str] = []
    scanned_rows = 0

    def _finalize_current_trip(trip_id: str | None, stop_sequence: list[str]) -> None:
        if trip_id is None or not stop_sequence:
            return
        route_id, _service_id, direction_id = trip_meta.get(trip_id, (None, None, None))
        pattern_key: PatternKey = (route_id, direction_id, tuple(stop_sequence))
        pattern_id = pattern_key_to_id.get(pattern_key)
        if pattern_id is None:
            pattern_id = _pattern_id_from_key(pattern_key)
            suffix = 1
            while (
                pattern_id in pattern_key_to_id.values()
                and pattern_key_to_id.get(pattern_key) != pattern_id
            ):
                suffix += 1
                pattern_id = f"{pattern_id}_{suffix}"
            pattern_key_to_id[pattern_key] = pattern_id
        trip_to_pattern_id[trip_id] = pattern_id

    for trip_id, stop_id, _stop_sequence in stop_time_rows:
        if not trip_id or not stop_id:
            continue
        if trip_id != current_trip_id:
            _finalize_current_trip(current_trip_id, current_trip_stop_sequence)
            current_trip_id = trip_id
            current_trip_stop_sequence = []
        current_trip_stop_sequence.append(parent_map.get(stop_id, stop_id))
        scanned_rows += 1
        if progress and scanned_rows % progress_every == 0:
            print(
                "Scanned "
                f"{scanned_rows} stop_times rows while building trip patterns..."
            )
    _finalize_current_trip(current_trip_id, current_trip_stop_sequence)
    if progress:
        print(
            "Identified "
            f"{len(set(trip_to_pattern_id.values()))} unique pattern(s) "
            f"from {len(trip_to_pattern_id)} trip(s)."
        )
    return trip_to_pattern_id


def build_trip_stop_graph_from_gtfs(
    session: Session,
    feed_id: str,
    *,
    connect_same_stop_transfers: bool = True,
    same_stop_transfer_sec: int = DEFAULT_SAME_STOP_TRANSFER_SEC,
    transfer_edge_penalty_sec: int = DEFAULT_TRANSFER_EDGE_PENALTY_SEC,
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
    if transfer_edge_penalty_sec < 0:
        raise ValueError("transfer_edge_penalty_sec must be >= 0.")

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
        canonical_stop_id = parent_station or stop_id
        parent_map[stop_id] = canonical_stop_id
        if stop_lat is not None and stop_lon is not None:
            parent_stop_coords.setdefault(
                canonical_stop_id,
                (float(stop_lat), float(stop_lon)),
            )
        stop_count += 1
        if progress and stop_count % progress_every == 0:
            print(f"Loaded {stop_count} stops for trip-stop graph...")
    if progress:
        print(f"Loaded {stop_count} stops for trip-stop graph total.")

    trip_meta: dict[str, tuple[str | None, str | None, int | None]] = {}
    trip_rows = (
        session.query(Trip.trip_id, Trip.route_id, Trip.service_id, Trip.direction_id)
        .filter(Trip.feed_id == feed_id)
        .yield_per(5000)
    )
    for trip_id, route_id, service_id, direction_id in trip_rows:
        if not trip_id:
            continue
        trip_meta[trip_id] = (route_id, service_id, direction_id)

    trip_to_pattern_id = _build_trip_pattern_map(
        session=session,
        feed_id=feed_id,
        parent_map=parent_map,
        trip_meta=trip_meta,
        progress=progress,
        progress_every=progress_every,
    )

    graph = TripStopGraph()
    graph.trip_to_pattern_id = trip_to_pattern_id

    def _ensure_node(stop_id: str, trip_id: str) -> str | None:
        pattern_id = trip_to_pattern_id.get(trip_id)
        if pattern_id is None:
            return None
        canonical_stop_id = parent_map.get(stop_id, stop_id)
        route_stop_id = make_trip_stop_node_id(canonical_stop_id, pattern_id)
        if route_stop_id in graph.nodes:
            return route_stop_id
        stop_lat, stop_lon = parent_stop_coords.get(canonical_stop_id, (None, None))
        route_id, service_id, direction_id = trip_meta.get(trip_id, (None, None, None))
        graph.add_node(
            route_stop_id,
            stop_id=canonical_stop_id,
            pattern_id=pattern_id,
            route_id=route_id,
            service_id=service_id,
            direction_id=direction_id,
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
        if trip_id not in trip_to_pattern_id:
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
            if from_node and to_node and from_node != to_node:
                dep_time = prev_departure_time or prev_arrival_time
                arr_time = arrival_time or departure_time
                weight_sec, dep_sec, arr_sec = _edge_timing(dep_time, arr_time)
                route_id, _service_id, _direction_id = trip_meta.get(
                    trip_id, (None, None, None)
                )
                if dep_sec is not None and arr_sec is not None:
                    graph.add_ride_departure(
                        from_node,
                        to_route_stop_id=to_node,
                        dep_time_sec=dep_sec,
                        arr_time_sec=arr_sec,
                        trip_id=trip_id,
                        route_id=route_id,
                    )
                elif weight_sec is not None:
                    graph.add_edge(
                        from_node,
                        TripStopEdge(
                            to_route_stop_id=to_node,
                            weight_sec=weight_sec,
                            kind="ride",
                            trip_id=trip_id,
                            route_id=route_id,
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

    hub_exit_initialized_for_stop: set[str] = set()

    def _ensure_same_stop_transfer_hub_exit_edges(stop_id: str) -> str | None:
        route_stop_ids = graph.route_stop_ids_for_stop(stop_id)
        if not route_stop_ids:
            return None
        stop_lat, stop_lon = parent_stop_coords.get(stop_id, (None, None))
        same_stop_transfer_hub_node = graph.ensure_same_stop_transfer_hub(
            stop_id=stop_id,
            stop_lat=cast(float | None, stop_lat),
            stop_lon=cast(float | None, stop_lon),
        )
        if stop_id in hub_exit_initialized_for_stop:
            return same_stop_transfer_hub_node
        for route_stop_id in sorted(route_stop_ids):
            graph.add_transfer_edge(
                same_stop_transfer_hub_node,
                to_route_stop_id=route_stop_id,
                weight_sec=_with_transfer_edge_penalty(0, transfer_edge_penalty_sec),
                transfer_type=2,
                apply_penalty=False,
                label="station_link",
            )
        hub_exit_initialized_for_stop.add(stop_id)
        return same_stop_transfer_hub_node

    same_stop_transfer_count = 0
    if connect_same_stop_transfers:
        for stop_id, route_stop_ids in graph.stop_to_route_stop_ids.items():
            if len(route_stop_ids) < 2:
                continue
            route_stop_id_list = sorted(route_stop_ids)
            same_stop_transfer_hub_node = _ensure_same_stop_transfer_hub_exit_edges(
                stop_id
            )
            if same_stop_transfer_hub_node is None:
                continue
            same_stop_transfer_count += len(route_stop_id_list)
            for route_stop_id in route_stop_id_list:
                graph.add_transfer_edge(
                    route_stop_id,
                    to_route_stop_id=same_stop_transfer_hub_node,
                    weight_sec=_with_transfer_edge_penalty(
                        same_stop_transfer_sec,
                        transfer_edge_penalty_sec,
                    ),
                    transfer_type=2,
                    label="station_link",
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
        from_nodes = sorted(graph.route_stop_ids_for_stop(from_stop))
        to_nodes = sorted(graph.route_stop_ids_for_stop(to_stop))
        to_hub_node = _ensure_same_stop_transfer_hub_exit_edges(to_stop)
        if to_hub_node is None:
            continue
        for from_node in from_nodes:
            graph.add_transfer_edge(
                from_node,
                to_route_stop_id=to_hub_node,
                weight_sec=_with_transfer_edge_penalty(
                    min_transfer_time,
                    transfer_edge_penalty_sec,
                ),
                transfer_type=transfer_type,
            )
            explicit_transfer_count += 1
            if progress and explicit_transfer_count % progress_every == 0:
                print(
                    "Added "
                    f"{explicit_transfer_count} inter-stop transfer edges so far..."
                )
        if symmetric_transfers:
            explicit_stop_pairs.add((to_stop, from_stop))
            from_hub_node = _ensure_same_stop_transfer_hub_exit_edges(from_stop)
            if from_hub_node is None:
                continue
            for to_node in to_nodes:
                graph.add_transfer_edge(
                    to_node,
                    to_route_stop_id=from_hub_node,
                    weight_sec=_with_transfer_edge_penalty(
                        min_transfer_time,
                        transfer_edge_penalty_sec,
                    ),
                    transfer_type=transfer_type,
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
            from_nodes = sorted(graph.route_stop_ids_for_stop(spec.from_stop_id))
            to_hub_node = _ensure_same_stop_transfer_hub_exit_edges(spec.to_stop_id)
            if to_hub_node is None:
                continue
            for from_node in from_nodes:
                graph.add_transfer_edge(
                    from_node,
                    to_route_stop_id=to_hub_node,
                    weight_sec=_with_transfer_edge_penalty(
                        spec.duration_sec,
                        transfer_edge_penalty_sec,
                    ),
                    transfer_type=None,
                    apply_penalty=False,
                    label=WALK_EDGE_LABEL,
                )
                walk_edge_count += 1
                if progress and walk_edge_count % progress_every == 0:
                    print(
                        f"Added {walk_edge_count}/{len(walk_specs)} walking edges so far in trip-stop graph..."
                    )
        if progress:
            print(f"Added {walk_edge_count} walking edges in trip-stop graph.")

    graph.finalize()
    return graph
