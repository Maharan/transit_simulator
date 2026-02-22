from __future__ import annotations

from types import SimpleNamespace

from core.graph.graph_methods.synthetic_edge import SyntheticEdge


def test_from_edge_copies_fields_and_defaults() -> None:
    raw_edge = SimpleNamespace(
        to_stop_id="to-stop",
        weight_sec=120,
        kind="transfer",
        route_id="route-1",
        trip_id="trip-1",
        dep_time="10:00:00",
        arr_time="10:02:00",
        dep_time_sec=36000,
        arr_time_sec=36120,
        transfer_type=2,
        apply_penalty=True,
    )

    edge = SyntheticEdge.from_edge(raw_edge)
    assert edge.to_stop_id == "to-stop"
    assert edge.weight_sec == 120
    assert edge.route_id == "route-1"
    assert edge.trip_id == "trip-1"
    assert edge.apply_penalty is True
    assert edge.label is None


def test_from_edge_respects_explicit_overrides() -> None:
    raw_edge = SimpleNamespace(
        to_stop_id="to-stop",
        weight_sec=5,
        kind="trip",
        apply_penalty=True,
    )

    edge = SyntheticEdge.from_edge(
        raw_edge,
        kind="transfer",
        apply_penalty=False,
        label="station_link",
    )
    assert edge.kind == "transfer"
    assert edge.apply_penalty is False
    assert edge.label == "station_link"
