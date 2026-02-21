from __future__ import annotations

from types import SimpleNamespace

from core.graph.lite import GraphLite


def test_graph_lite_compresses_ids_and_preserves_transfer_fields() -> None:
    transfer_edge = SimpleNamespace(
        to_stop_id="B",
        weight_sec=42,
        transfer_type=2,
        apply_penalty=False,
        label="walk",
    )
    trip_bucket = SimpleNamespace(
        to_stop_id="C",
        dep_secs=[3600, 7200],
        arr_secs=[3660, 7260],
        trip_ids=["trip-1", None],
        route_ids=["route-1", None],
        last_dep=7200,
    )
    graph = SimpleNamespace(
        transfer_edges={"A": [transfer_edge]},
        trip_buckets={"A": [trip_bucket]},
    )

    lite = GraphLite.from_graph(graph)
    transfer = lite.transfer_edges_from("A")[0]
    bucket = lite.trip_buckets_from("A")[0]

    assert transfer.to_stop_id == "B"
    assert transfer.label == "walk"
    assert transfer.apply_penalty is False
    assert list(bucket.trip_ids) == [1, 0]
    assert list(bucket.route_ids) == [1, 0]
    assert lite.trip_id_for(1) == "trip-1"
    assert lite.route_id_for(1) == "route-1"


def test_graph_lite_lookup_helpers_handle_zero_and_missing_indexes() -> None:
    lite = GraphLite()
    assert lite.route_id_for(0) is None
    assert lite.trip_id_for(0) is None
    assert lite.route_id_for(999) is None
    assert lite.trip_id_for(999) is None


def test_graph_lite_edges_from_returns_transfer_edges() -> None:
    graph = SimpleNamespace(
        transfer_edges={
            "A": [
                SimpleNamespace(
                    to_stop_id="B",
                    weight_sec=50,
                    transfer_type=None,
                    apply_penalty=True,
                    label=None,
                )
            ]
        },
        trip_buckets={},
    )
    lite = GraphLite.from_graph(graph)

    assert lite.edges_from("A") == lite.transfer_edges_from("A")
