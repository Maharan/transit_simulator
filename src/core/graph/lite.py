from __future__ import annotations

from array import array
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TransferEdgeLite:
    to_stop_id: str
    weight_sec: int | None
    transfer_type: int | None
    apply_penalty: bool = True
    label: str | None = None
    kind: str = "transfer"
    route_id: str | None = None
    trip_id: str | None = None
    dep_time: str | None = None
    arr_time: str | None = None
    dep_time_sec: int | None = None
    arr_time_sec: int | None = None


@dataclass(frozen=True, slots=True)
class TripBucketLite:
    to_stop_id: str
    dep_secs: array
    arr_secs: array
    trip_ids: array
    route_ids: array
    last_dep: int


class GraphLite:
    def __init__(self) -> None:
        self.transfer_edges: dict[str, list[TransferEdgeLite]] = {}
        self.trip_buckets: dict[str, list[TripBucketLite]] = {}
        self.route_id_by_index: list[str | None] = [None]
        self.trip_id_by_index: list[str | None] = [None]

    @classmethod
    def from_graph(cls, graph) -> "GraphLite":
        lite = cls()
        route_id_to_index: dict[str, int] = {}
        trip_id_to_index: dict[str, int] = {}

        for stop_id, edges in getattr(graph, "transfer_edges", {}).items():
            lite.transfer_edges[stop_id] = [
                TransferEdgeLite(
                    to_stop_id=edge.to_stop_id,
                    weight_sec=edge.weight_sec,
                    transfer_type=edge.transfer_type,
                    apply_penalty=getattr(edge, "apply_penalty", True),
                    label=getattr(edge, "label", None),
                )
                for edge in edges
            ]

        for stop_id, buckets in getattr(graph, "trip_buckets", {}).items():
            lite_buckets: list[TripBucketLite] = []
            for bucket in buckets:
                dep_secs = array("I", bucket.dep_secs)
                arr_secs = array("I", bucket.arr_secs)
                trip_ids = array("I")
                route_ids = array("I")
                for trip_id, route_id in zip(bucket.trip_ids, bucket.route_ids):
                    if trip_id:
                        trip_index = trip_id_to_index.get(trip_id)
                        if trip_index is None:
                            trip_index = len(lite.trip_id_by_index)
                            lite.trip_id_by_index.append(trip_id)
                            trip_id_to_index[trip_id] = trip_index
                        trip_ids.append(trip_index)
                    else:
                        trip_ids.append(0)

                    if route_id:
                        route_index = route_id_to_index.get(route_id)
                        if route_index is None:
                            route_index = len(lite.route_id_by_index)
                            lite.route_id_by_index.append(route_id)
                            route_id_to_index[route_id] = route_index
                        route_ids.append(route_index)
                    else:
                        route_ids.append(0)

                lite_buckets.append(
                    TripBucketLite(
                        to_stop_id=bucket.to_stop_id,
                        dep_secs=dep_secs,
                        arr_secs=arr_secs,
                        trip_ids=trip_ids,
                        route_ids=route_ids,
                        last_dep=bucket.last_dep,
                    )
                )
            lite.trip_buckets[stop_id] = lite_buckets

        return lite

    def route_id_for(self, index: int | None) -> str | None:
        if not index:
            return None
        if 0 <= index < len(self.route_id_by_index):
            return self.route_id_by_index[index]
        return None

    def trip_id_for(self, index: int | None) -> str | None:
        if not index:
            return None
        if 0 <= index < len(self.trip_id_by_index):
            return self.trip_id_by_index[index]
        return None

    def transfer_edges_from(self, stop_id: str):
        return self.transfer_edges.get(stop_id, [])

    def trip_buckets_from(self, stop_id: str):
        return self.trip_buckets.get(stop_id, [])

    def edges_from(self, stop_id: str):
        return self.transfer_edges.get(stop_id, [])
