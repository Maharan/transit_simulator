from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from graph.models import GraphEdge, GraphNode
from graph.synthetic_edge import SyntheticEdge
from gtfs.models import Stop, StopTime, Transfer, Trip


@dataclass(frozen=True)
class Edge:
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
class TripBucket:
    to_stop_id: str
    dep_secs: list[int]
    arr_secs: list[int]
    trip_ids: list[str | None]
    route_ids: list[str | None]
    last_dep: int


class Graph(object):
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, float | None]] = {}
        self.adjacency: dict[str, list[Edge]] = defaultdict(list)
        self.transfer_edges: dict[str, list[Edge]] = defaultdict(list)
        self.trip_buckets: dict[str, list[TripBucket]] = defaultdict(list)

    def add_node(
        self, stop_id: str, stop_lat: float | None, stop_lon: float | None
    ) -> None:
        self.nodes[stop_id] = {"stop_lat": stop_lat, "stop_lon": stop_lon}

    def add_edge(self, from_stop_id: str, edge: Edge) -> None:
        self.adjacency[from_stop_id].append(edge)
        if edge.kind == "transfer":
            self.transfer_edges[from_stop_id].append(edge)

    def edges_from(self, stop_id: str) -> list[Edge]:
        return self.adjacency.get(stop_id, [])

    def transfer_edges_from(self, stop_id: str) -> list[Edge]:
        return self.transfer_edges.get(stop_id, [])

    def trip_buckets_from(self, stop_id: str) -> list[TripBucket]:
        return self.trip_buckets.get(stop_id, [])


def _time_to_seconds(time_str: str | None) -> int | None:
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


def _edge_timing(
    dep_time: str | None, arr_time: str | None
) -> tuple[int | None, int | None, int | None]:
    dep_sec = _time_to_seconds(dep_time)
    arr_sec = _time_to_seconds(arr_time)
    if dep_sec is None or arr_sec is None:
        return None, dep_sec, arr_sec
    weight = arr_sec - dep_sec
    if weight < 0:
        return None, dep_sec, arr_sec
    return weight, dep_sec, arr_sec


def build_graph_from_gtfs(
    session: Session,
    feed_id: str,
    symmetric_transfers: bool = False,
    progress: bool = False,
    progress_every: int = 5000,
) -> tuple[Graph, list[GraphEdge]]:
    graph = Graph()
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
    stop_count = 0
    for stop_id, stop_lat, stop_lon, parent_station in stops:
        if not stop_id:
            continue
        if parent_station:
            parent_map[stop_id] = parent_station
            parent_pairs.append((stop_id, parent_station))
        else:
            parent_map[stop_id] = stop_id
        graph.add_node(stop_id, stop_lat, stop_lon)
        stop_count += 1
        if progress and stop_count % progress_every == 0:
            print(f"Loaded {stop_count} stops...")
    if progress:
        print(f"Loaded {stop_count} stops total.")
        print(f"Found {len(parent_pairs)} child stops with parent stations.")

    trip_meta = {}
    trip_rows = (
        session.query(Trip.trip_id, Trip.route_id, Trip.service_id)
        .filter(Trip.feed_id == feed_id)
        .yield_per(5000)
    )
    for trip_id, route_id, service_id in trip_rows:
        if not trip_id:
            continue
        trip_meta[trip_id] = (route_id, service_id)

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
            route_id, service_id = trip_meta.get(trip_id, (None, None))
            from_node = parent_map.get(prev_stop_id, prev_stop_id)
            to_node = parent_map.get(stop_id, stop_id)
            if from_node != to_node:
                add_edge(
                    from_stop_id=from_node,
                    to_stop_id=to_node,
                    kind="trip",
                    weight_sec=weight_sec,
                    trip_id=trip_id,
                    route_id=route_id,
                    service_id=service_id,
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
                        (dep_sec, arr_sec, trip_id, route_id)
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
        progress: bool = False,
        progress_every: int = 5000,
    ) -> None:
        self._session = session
        self._feed_id = feed_id
        self._symmetric_transfers = symmetric_transfers
        self._progress = progress
        self._progress_every = progress_every
        self._ensure_cache_table()
        if rebuild:
            self._graph = self.rebuild()
        else:
            self._graph = self.load_or_build()

    @property
    def graph(self) -> Graph:
        return self._graph

    def load_or_build(self) -> Graph:
        if self._has_cache():
            return self._load_graph_from_cache()
        return self.rebuild()

    def rebuild(self) -> Graph:
        self._delete_cache()
        graph, edges = build_graph_from_gtfs(
            session=self._session,
            feed_id=self._feed_id,
            symmetric_transfers=self._symmetric_transfers,
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

    def _load_graph_from_cache(self) -> Graph:
        graph = Graph()
        trip_bucket_entries: dict[
            tuple[str, str], list[tuple[int, int, str | None, str | None]]
        ] = {}
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
            self._session.query(GraphEdge)
            .filter(GraphEdge.feed_id == self._feed_id)
            .order_by(GraphEdge.id)
            .yield_per(5000)
        )
        for edge in cached_edges:
            if (
                edge.kind == "transfer"
                and edge.transfer_type == 2
                and (edge.weight_sec or 0) == 0
            ):
                graph.add_edge(
                    edge.from_stop_id,
                    SyntheticEdge.from_edge(
                        edge, label="station_link", apply_penalty=False
                    ),
                )
                continue
            dep_sec = _time_to_seconds(edge.dep_time)
            arr_sec = _time_to_seconds(edge.arr_time)
            graph.add_edge(
                edge.from_stop_id,
                Edge(
                    to_stop_id=edge.to_stop_id,
                    weight_sec=edge.weight_sec,
                    kind=edge.kind,
                    trip_id=edge.trip_id,
                    route_id=edge.route_id,
                    service_id=edge.service_id,
                    dep_time=edge.dep_time,
                    arr_time=edge.arr_time,
                    dep_time_sec=dep_sec,
                    arr_time_sec=arr_sec,
                    transfer_type=edge.transfer_type,
                    stop_sequence=edge.stop_sequence,
                    apply_penalty=True,
                    label=None,
                ),
            )
            if (
                edge.kind == "trip"
                and dep_sec is not None
                and arr_sec is not None
                and edge.from_stop_id is not None
                and edge.to_stop_id is not None
            ):
                key = (edge.from_stop_id, edge.to_stop_id)
                trip_bucket_entries.setdefault(key, []).append(
                    (dep_sec, arr_sec, edge.trip_id, edge.route_id)
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
        return graph
