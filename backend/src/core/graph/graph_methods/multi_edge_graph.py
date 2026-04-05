from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .base import BaseGraph
from .gtfs_support import (
    DEFAULT_WALK_MAX_DISTANCE_M,
    DEFAULT_WALK_MAX_NEIGHBORS,
    DEFAULT_WALK_SPEED_MPS,
    EMPTY_TRIP_BUILD_METADATA,
    edge_timing,
    load_parent_stop_coords,
    load_trip_metadata,
    time_to_seconds,
)
from core.graph.models import GraphEdge, GraphNode
from .synthetic_edge import SyntheticEdge
from core.graph.walk import WALK_EDGE_LABEL, build_walk_edges
from core.gtfs.models import Stop, StopTime, Transfer


@dataclass(frozen=True)
class MultiGraphEdge:
    to_stop_id: str
    weight_sec: int | None
    kind: str
    trip_id: str | None = None
    route_id: str | None = None
    service_id: str | None = None
    dep_time: str | None = None
    arr_time: str | None = None
    dep_time_sec: int | None = None
    arr_time_sec: int | None = None
    transfer_type: int | None = None
    stop_sequence: int | None = None
    apply_penalty: bool = True
    label: str | None = None


@dataclass(frozen=True)
class MultiGraphTripBucket:
    to_stop_id: str
    dep_secs: list[int]
    arr_secs: list[int]
    trip_ids: list[str | None]
    route_ids: list[str | None]
    last_dep: int


class MultiGraph(BaseGraph):
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, float | None]] = {}
        self.adjacency: dict[str, list[MultiGraphEdge]] = defaultdict(list)
        self.transfer_edges: dict[str, list[MultiGraphEdge]] = defaultdict(list)
        self.trip_buckets: dict[str, list[MultiGraphTripBucket]] = defaultdict(list)

    def add_node(
        self, stop_id: str, stop_lat: float | None, stop_lon: float | None
    ) -> None:
        self.nodes[stop_id] = {"stop_lat": stop_lat, "stop_lon": stop_lon}

    def add_edge(self, from_stop_id: str, edge: MultiGraphEdge) -> None:
        self.adjacency[from_stop_id].append(edge)
        if edge.kind == "transfer":
            self.transfer_edges[from_stop_id].append(edge)

    def edges_from(self, stop_id: str) -> list[MultiGraphEdge]:
        return self.adjacency.get(stop_id, [])

    def transfer_edges_from(self, stop_id: str) -> list[MultiGraphEdge]:
        return self.transfer_edges.get(stop_id, [])

    def trip_buckets_from(self, stop_id: str) -> list[MultiGraphTripBucket]:
        return self.trip_buckets.get(stop_id, [])


# Backward-compatible aliases for existing callers.
Edge = MultiGraphEdge
TripBucket = MultiGraphTripBucket
Graph = MultiGraph
_time_to_seconds = time_to_seconds
_edge_timing = edge_timing
_load_parent_stop_coords = load_parent_stop_coords


def _add_walk_edges(
    *,
    graph: MultiGraph,
    stop_coords: dict[str, tuple[float, float]],
    walk_max_distance_m: int,
    walk_speed_mps: float,
    walk_max_neighbors: int,
) -> int:
    existing_edges = {
        (from_stop_id, edge.to_stop_id)
        for from_stop_id, edges in graph.transfer_edges.items()
        for edge in edges
    }
    walk_edge_specs = build_walk_edges(
        stop_coords=stop_coords,
        max_distance_m=walk_max_distance_m,
        walking_speed_mps=walk_speed_mps,
        max_neighbors=walk_max_neighbors,
        existing_edges=existing_edges,
    )
    for spec in walk_edge_specs:
        graph.add_edge(
            spec.from_stop_id,
            Edge(
                to_stop_id=spec.to_stop_id,
                weight_sec=spec.duration_sec,
                kind="transfer",
                transfer_type=None,
                apply_penalty=False,
                label=WALK_EDGE_LABEL,
            ),
        )
    return len(walk_edge_specs)


def build_graph_from_gtfs(
    session: Session,
    feed_id: str,
    symmetric_transfers: bool = False,
    enable_walking: bool = True,
    walk_max_distance_m: int = DEFAULT_WALK_MAX_DISTANCE_M,
    walk_speed_mps: float = DEFAULT_WALK_SPEED_MPS,
    walk_max_neighbors: int = DEFAULT_WALK_MAX_NEIGHBORS,
    progress: bool = False,
    progress_every: int = 5000,
) -> tuple[MultiGraph, list[GraphEdge]]:
    graph = MultiGraph()
    edges: list[GraphEdge] = []
    trip_bucket_entries: dict[
        tuple[str, str], list[tuple[int, int, str | None, str | None]]
    ] = {}

    stops = (
        session.query(Stop.stop_id, Stop.stop_lat, Stop.stop_lon, Stop.parent_station)
        .filter(Stop.feed_id == feed_id)
        .yield_per(5000)
    )
    parent_map: dict[str, str] = {}
    parent_pairs: list[tuple[str, str]] = []
    parent_stop_coords: dict[str, tuple[float, float]] = {}
    stop_count = 0
    for stop_id, stop_lat, stop_lon, parent_station in stops:
        if not stop_id:
            continue
        if parent_station:
            node_id = parent_station
            parent_map[stop_id] = node_id
            parent_pairs.append((stop_id, parent_station))
        else:
            node_id = stop_id
            parent_map[stop_id] = node_id
        if stop_lat is not None and stop_lon is not None:
            parent_stop_coords.setdefault(node_id, (float(stop_lat), float(stop_lon)))
        graph.add_node(stop_id, stop_lat, stop_lon)
        stop_count += 1
        if progress and stop_count % progress_every == 0:
            print(f"Loaded {stop_count} stops...")
    if progress:
        print(f"Loaded {stop_count} stops total.")
        print(f"Found {len(parent_pairs)} child stops with parent stations.")

    trip_meta = load_trip_metadata(session, feed_id)

    def add_edge(
        from_stop_id: str,
        to_stop_id: str,
        kind: str,
        weight_sec: int | None,
        trip_id: str | None = None,
        route_id: str | None = None,
        service_id: str | None = None,
        dep_time: str | None = None,
        arr_time: str | None = None,
        dep_time_sec: int | None = None,
        arr_time_sec: int | None = None,
        transfer_type: int | None = None,
        stop_sequence: int | None = None,
        apply_penalty: bool = True,
        label: str | None = None,
    ) -> None:
        edge = Edge(
            to_stop_id=to_stop_id,
            weight_sec=weight_sec,
            kind=kind,
            trip_id=trip_id,
            route_id=route_id,
            service_id=service_id,
            dep_time=dep_time,
            arr_time=arr_time,
            dep_time_sec=dep_time_sec,
            arr_time_sec=arr_time_sec,
            transfer_type=transfer_type,
            stop_sequence=stop_sequence,
            apply_penalty=apply_penalty,
            label=label,
        )
        graph.add_edge(from_stop_id, edge)
        edges.append(
            GraphEdge(
                feed_id=feed_id,
                from_stop_id=from_stop_id,
                to_stop_id=to_stop_id,
                kind=kind,
                weight_sec=weight_sec,
                trip_id=trip_id,
                route_id=route_id,
                service_id=service_id,
                dep_time=dep_time,
                arr_time=arr_time,
                transfer_type=transfer_type,
                stop_sequence=stop_sequence,
            )
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
    transfer_count = 0
    for from_stop_id, to_stop_id, min_transfer_time, transfer_type in transfer_rows:
        if not from_stop_id or not to_stop_id:
            continue
        from_node = parent_map.get(from_stop_id, from_stop_id)
        to_node = parent_map.get(to_stop_id, to_stop_id)
        if from_node == to_node:
            continue
        add_edge(
            from_stop_id=from_node,
            to_stop_id=to_node,
            kind="transfer",
            weight_sec=min_transfer_time,
            transfer_type=transfer_type,
        )
        if symmetric_transfers and from_node != to_node:
            add_edge(
                from_stop_id=to_node,
                to_stop_id=from_node,
                kind="transfer",
                weight_sec=min_transfer_time,
                transfer_type=transfer_type,
            )

        transfer_count += 1
        if progress and transfer_count % progress_every == 0:
            print(f"Loaded {transfer_count} transfers...")
    if progress:
        print(f"Loaded {transfer_count} transfers total.")

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

    current_trip_id = None
    prev_stop_id = None
    prev_stop_sequence = None
    prev_arrival_time = None
    prev_departure_time = None

    stop_time_count = 0
    edge_count = 0
    for trip_id, stop_id, stop_sequence, arrival_time, departure_time in stop_time_rows:
        if not trip_id or not stop_id:
            continue
        if trip_id != current_trip_id:
            current_trip_id = trip_id
            prev_stop_id = stop_id
            prev_stop_sequence = stop_sequence
            prev_arrival_time = arrival_time
            prev_departure_time = departure_time
            continue

        if prev_stop_id:
            dep_time = prev_departure_time or prev_arrival_time
            arr_time = arrival_time or departure_time
            weight_sec, dep_sec, arr_sec = _edge_timing(dep_time, arr_time)
            trip = trip_meta.get(trip_id, EMPTY_TRIP_BUILD_METADATA)
            from_node = parent_map.get(prev_stop_id, prev_stop_id)
            to_node = parent_map.get(stop_id, stop_id)
            if from_node != to_node:
                add_edge(
                    from_stop_id=from_node,
                    to_stop_id=to_node,
                    kind="trip",
                    weight_sec=weight_sec,
                    trip_id=trip_id,
                    route_id=trip.route_id,
                    service_id=trip.service_id,
                    dep_time=dep_time,
                    arr_time=arr_time,
                    dep_time_sec=dep_sec,
                    arr_time_sec=arr_sec,
                    stop_sequence=prev_stop_sequence,
                )
                edge_count += 1
                if dep_sec is not None and arr_sec is not None:
                    key = (from_node, to_node)
                    trip_bucket_entries.setdefault(key, []).append(
                        (dep_sec, arr_sec, trip_id, trip.route_id)
                    )

        prev_stop_id = stop_id
        prev_stop_sequence = stop_sequence
        prev_arrival_time = arrival_time
        prev_departure_time = departure_time
        stop_time_count += 1
        if progress and stop_time_count % progress_every == 0:
            print(f"Scanned {stop_time_count} stop_times rows...")
    if progress:
        print(f"Scanned {stop_time_count} stop_times rows total.")
        print(f"Built {edge_count} trip edges.")

    if trip_bucket_entries:
        for (from_node, to_node), entries in trip_bucket_entries.items():
            entries.sort(key=lambda item: item[0])
            dep_secs = [item[0] for item in entries]
            arr_secs = [item[1] for item in entries]
            trip_ids = [item[2] for item in entries]
            route_ids = [item[3] for item in entries]
            graph.trip_buckets[from_node].append(
                TripBucket(
                    to_stop_id=to_node,
                    dep_secs=dep_secs,
                    arr_secs=arr_secs,
                    trip_ids=trip_ids,
                    route_ids=route_ids,
                    last_dep=dep_secs[-1],
                )
            )

    if enable_walking:
        walk_edge_count = _add_walk_edges(
            graph=graph,
            stop_coords=parent_stop_coords,
            walk_max_distance_m=walk_max_distance_m,
            walk_speed_mps=walk_speed_mps,
            walk_max_neighbors=walk_max_neighbors,
        )
        if progress:
            print(f"Added {walk_edge_count} walking edges.")

    if parent_pairs:
        parent_edge_count = 0
        for child_id, parent_id in parent_pairs:
            graph.add_edge(
                child_id,
                SyntheticEdge(
                    to_stop_id=parent_id,
                    weight_sec=0,
                    transfer_type=2,
                    label="station_link",
                    apply_penalty=False,
                ),
            )
            edges.append(
                GraphEdge(
                    feed_id=feed_id,
                    from_stop_id=child_id,
                    to_stop_id=parent_id,
                    kind="transfer",
                    weight_sec=0,
                    transfer_type=2,
                )
            )
            graph.add_edge(
                parent_id,
                SyntheticEdge(
                    to_stop_id=child_id,
                    weight_sec=0,
                    transfer_type=2,
                    label="station_link",
                    apply_penalty=False,
                ),
            )
            edges.append(
                GraphEdge(
                    feed_id=feed_id,
                    from_stop_id=parent_id,
                    to_stop_id=child_id,
                    kind="transfer",
                    weight_sec=0,
                    transfer_type=2,
                )
            )
            parent_edge_count += 2
            if progress and parent_edge_count % progress_every == 0:
                print(f"Added {parent_edge_count} parent transfer edges...")
        if progress:
            print(f"Added {parent_edge_count} parent transfer edges total.")

    return graph, edges


class GraphCache(object):
    def __init__(
        self,
        session: Session,
        feed_id: str,
        rebuild: bool = False,
        symmetric_transfers: bool = False,
        enable_walking: bool = True,
        walk_max_distance_m: int = DEFAULT_WALK_MAX_DISTANCE_M,
        walk_speed_mps: float = DEFAULT_WALK_SPEED_MPS,
        walk_max_neighbors: int = DEFAULT_WALK_MAX_NEIGHBORS,
        progress: bool = False,
        progress_every: int = 5000,
    ) -> None:
        self._session = session
        self._feed_id = feed_id
        self._symmetric_transfers = symmetric_transfers
        self._enable_walking = enable_walking
        self._walk_max_distance_m = walk_max_distance_m
        self._walk_speed_mps = walk_speed_mps
        self._walk_max_neighbors = walk_max_neighbors
        self._progress = progress
        self._progress_every = progress_every
        self._ensure_cache_table()
        if rebuild:
            self._graph = self.rebuild()
        else:
            self._graph = self.load_or_build()

    @property
    def graph(self) -> MultiGraph:
        return self._graph

    def load_or_build(self) -> MultiGraph:
        if self._has_cache():
            return self._load_graph_from_cache()
        return self.rebuild()

    def rebuild(self) -> MultiGraph:
        self._delete_cache()
        graph, edges = build_graph_from_gtfs(
            session=self._session,
            feed_id=self._feed_id,
            symmetric_transfers=self._symmetric_transfers,
            enable_walking=self._enable_walking,
            walk_max_distance_m=self._walk_max_distance_m,
            walk_speed_mps=self._walk_speed_mps,
            walk_max_neighbors=self._walk_max_neighbors,
            progress=self._progress,
            progress_every=self._progress_every,
        )
        if graph.nodes:
            node_rows = [
                GraphNode(
                    feed_id=self._feed_id,
                    stop_id=stop_id,
                    stop_lat=values["stop_lat"],
                    stop_lon=values["stop_lon"],
                )
                for stop_id, values in graph.nodes.items()
            ]
            self._session.bulk_save_objects(node_rows)
        if edges:
            self._session.bulk_save_objects(edges)
        self._session.commit()
        return graph

    def _ensure_cache_table(self) -> None:
        bind = self._session.get_bind()
        if bind is None:
            raise ValueError("Session is not bound to an engine.")
        GraphEdge.__table__.create(bind=bind, checkfirst=True)
        GraphNode.__table__.create(bind=bind, checkfirst=True)
        for index in GraphEdge.__table__.indexes:
            index.create(bind=bind, checkfirst=True)
        for index in GraphNode.__table__.indexes:
            index.create(bind=bind, checkfirst=True)

    def _has_cache(self) -> bool:
        row = (
            self._session.query(GraphEdge.id)
            .filter(GraphEdge.feed_id == self._feed_id)
            .first()
        )
        return row is not None

    def _delete_cache(self) -> None:
        (
            self._session.query(GraphEdge)
            .filter(GraphEdge.feed_id == self._feed_id)
            .delete(synchronize_session=False)
        )
        (
            self._session.query(GraphNode)
            .filter(GraphNode.feed_id == self._feed_id)
            .delete(synchronize_session=False)
        )
        self._session.flush()

    def _load_graph_from_cache(self) -> MultiGraph:
        graph = MultiGraph()
        trip_bucket_entries: dict[
            tuple[str, str], list[tuple[int, int, str | None, str | None]]
        ] = {}
        time_cache: dict[str, int | None] = {}

        def _cached_time_to_seconds(time_str: str | None) -> int | None:
            if time_str is None:
                return None
            cached = time_cache.get(time_str)
            if cached is not None or time_str in time_cache:
                return cached
            parsed = _time_to_seconds(time_str)
            time_cache[time_str] = parsed
            return parsed

        nodes = (
            self._session.query(
                GraphNode.stop_id, GraphNode.stop_lat, GraphNode.stop_lon
            )
            .filter(GraphNode.feed_id == self._feed_id)
            .yield_per(5000)
        )
        node_count = 0
        for stop_id, stop_lat, stop_lon in nodes:
            if not stop_id:
                continue
            graph.add_node(stop_id, stop_lat, stop_lon)
            node_count += 1

        if node_count == 0:
            stops = (
                self._session.query(Stop.stop_id, Stop.stop_lat, Stop.stop_lon)
                .filter(Stop.feed_id == self._feed_id)
                .yield_per(5000)
            )
            node_rows: list[GraphNode] = []
            for stop_id, stop_lat, stop_lon in stops:
                if not stop_id:
                    continue
                graph.add_node(stop_id, stop_lat, stop_lon)
                node_rows.append(
                    GraphNode(
                        feed_id=self._feed_id,
                        stop_id=stop_id,
                        stop_lat=stop_lat,
                        stop_lon=stop_lon,
                    )
                )
            if node_rows:
                self._session.bulk_save_objects(node_rows)
                self._session.flush()

        cached_edges = (
            self._session.query(
                GraphEdge.from_stop_id,
                GraphEdge.to_stop_id,
                GraphEdge.kind,
                GraphEdge.weight_sec,
                GraphEdge.trip_id,
                GraphEdge.route_id,
                GraphEdge.service_id,
                GraphEdge.dep_time,
                GraphEdge.arr_time,
                GraphEdge.transfer_type,
                GraphEdge.stop_sequence,
            )
            .filter(GraphEdge.feed_id == self._feed_id)
            .order_by(GraphEdge.id)
            .yield_per(20000)
        )
        for (
            from_stop_id,
            to_stop_id,
            kind,
            weight_sec,
            trip_id,
            route_id,
            service_id,
            dep_time,
            arr_time,
            transfer_type,
            stop_sequence,
        ) in cached_edges:
            if not from_stop_id or not to_stop_id:
                continue
            if kind == "transfer" and transfer_type == 2 and (weight_sec or 0) == 0:
                graph.add_edge(
                    from_stop_id,
                    SyntheticEdge(
                        to_stop_id=to_stop_id,
                        weight_sec=weight_sec,
                        transfer_type=transfer_type,
                        label="station_link",
                        apply_penalty=False,
                    ),
                )
                continue
            dep_sec = _cached_time_to_seconds(dep_time)
            arr_sec = _cached_time_to_seconds(arr_time)
            graph.add_edge(
                from_stop_id,
                Edge(
                    to_stop_id=to_stop_id,
                    weight_sec=weight_sec,
                    kind=kind,
                    trip_id=trip_id,
                    route_id=route_id,
                    service_id=service_id,
                    dep_time=dep_time,
                    arr_time=arr_time,
                    dep_time_sec=dep_sec,
                    arr_time_sec=arr_sec,
                    transfer_type=transfer_type,
                    stop_sequence=stop_sequence,
                    apply_penalty=True,
                    label=None,
                ),
            )
            if kind == "trip" and dep_sec is not None and arr_sec is not None:
                key = (from_stop_id, to_stop_id)
                trip_bucket_entries.setdefault(key, []).append(
                    (dep_sec, arr_sec, trip_id, route_id)
                )
        if trip_bucket_entries:
            for (from_node, to_node), entries in trip_bucket_entries.items():
                entries.sort(key=lambda item: item[0])
                dep_secs = [item[0] for item in entries]
                arr_secs = [item[1] for item in entries]
                trip_ids = [item[2] for item in entries]
                route_ids = [item[3] for item in entries]
                graph.trip_buckets[from_node].append(
                    TripBucket(
                        to_stop_id=to_node,
                        dep_secs=dep_secs,
                        arr_secs=arr_secs,
                        trip_ids=trip_ids,
                        route_ids=route_ids,
                        last_dep=dep_secs[-1],
                    )
                )

        if self._enable_walking:
            parent_stop_coords = _load_parent_stop_coords(
                self._session,
                self._feed_id,
                known_nodes=set(graph.nodes.keys()),
            )
            _add_walk_edges(
                graph=graph,
                stop_coords=parent_stop_coords,
                walk_max_distance_m=self._walk_max_distance_m,
                walk_speed_mps=self._walk_speed_mps,
                walk_max_neighbors=self._walk_max_neighbors,
            )
        return graph
