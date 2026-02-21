from __future__ import annotations

from typing import Iterable, Protocol


class EdgeLike(Protocol):
    to_stop_id: str
    weight_sec: int | None
    kind: str
    route_id: str | None
    trip_id: str | None
    dep_time: str | None
    arr_time: str | None
    transfer_type: int | None
    apply_penalty: bool | None
    label: str | None


class GraphLike(Protocol):
    def edges_from(self, stop_id: str) -> Iterable[EdgeLike]: ...


class ResultLike(Protocol):
    arrival_time_sec: int | None
    stop_path: list[str]
    edge_path: list[EdgeLike]
