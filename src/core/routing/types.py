from __future__ import annotations

from typing import Iterable, Protocol, Sequence


class EdgeLike(Protocol):
    to_stop_id: str
    weight_sec: int | None
    kind: str
    route_id: str | int | None
    trip_id: str | int | None
    dep_time: str | None
    arr_time: str | None
    dep_time_sec: int | None
    arr_time_sec: int | None
    transfer_type: int | None
    apply_penalty: bool
    label: str | None


class GraphLike(Protocol):
    def edges_from(self, stop_id: str) -> Iterable[EdgeLike]: ...

    def transfer_edges_from(self, stop_id: str) -> Iterable[EdgeLike]: ...

    def trip_buckets_from(self, stop_id: str) -> Iterable["TripBucketLike"]: ...


class TripBucketLike(Protocol):
    to_stop_id: str
    dep_secs: Sequence[int]
    arr_secs: Sequence[int]
    trip_ids: Sequence[int | str | None]
    route_ids: Sequence[int | str | None]
    last_dep: int


class ResultLike(Protocol):
    arrival_time_sec: int | None
    stop_path: list[str]
    edge_path: list[EdgeLike]
