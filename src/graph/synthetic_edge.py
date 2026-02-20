from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticEdge:
    """Virtual edge not stored in the graph cache (e.g., station/platform links)."""

    to_stop_id: str
    weight_sec: int | None
    kind: str = "transfer"
    route_id: str | None = None
    trip_id: str | None = None
    dep_time: str | None = None
    arr_time: str | None = None
    transfer_type: int | None = None
    apply_penalty: bool = False
    label: str | None = None

    @classmethod
    def from_edge(
        cls,
        edge: object,
        *,
        kind: str | None = None,
        apply_penalty: bool | None = None,
        label: str | None = None,
    ) -> "SyntheticEdge":
        return cls(
            to_stop_id=getattr(edge, "to_stop_id"),
            weight_sec=getattr(edge, "weight_sec", None),
            kind=kind or getattr(edge, "kind", "transfer"),
            route_id=getattr(edge, "route_id", None),
            trip_id=getattr(edge, "trip_id", None),
            dep_time=getattr(edge, "dep_time", None),
            arr_time=getattr(edge, "arr_time", None),
            transfer_type=getattr(edge, "transfer_type", None),
            apply_penalty=apply_penalty
            if apply_penalty is not None
            else getattr(edge, "apply_penalty", True),
            label=label,
        )
