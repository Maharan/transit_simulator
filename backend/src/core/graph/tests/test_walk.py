from __future__ import annotations

import pytest

from core.graph.walk import _project_stops, build_walk_edges


def test_build_walk_edges_creates_bidirectional_links() -> None:
    edges = build_walk_edges(
        stop_coords={
            "A": (53.5500, 9.9930),
            "B": (53.5510, 9.9930),
        },
        max_distance_m=200,
        walking_speed_mps=1.0,
        max_neighbors=4,
    )

    by_pair = {(edge.from_stop_id, edge.to_stop_id): edge for edge in edges}
    assert ("A", "B") in by_pair
    assert ("B", "A") in by_pair
    assert by_pair[("A", "B")].duration_sec == by_pair[("B", "A")].duration_sec
    assert 100 <= by_pair[("A", "B")].duration_sec <= 120


def test_build_walk_edges_respects_neighbor_limit_and_existing_edges() -> None:
    edges = build_walk_edges(
        stop_coords={
            "A": (53.5500, 9.9930),
            "B": (53.5506, 9.9930),
            "C": (53.5512, 9.9930),
        },
        max_distance_m=200,
        walking_speed_mps=1.4,
        max_neighbors=1,
        existing_edges={("A", "B")},
    )

    outgoing: dict[str, list[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge.from_stop_id, []).append(edge.to_stop_id)

    assert outgoing["A"] == ["C"]
    assert len(outgoing["B"]) == 1
    assert len(outgoing["C"]) == 1


def test_build_walk_edges_rejects_nonpositive_speed() -> None:
    with pytest.raises(ValueError, match="walking_speed_mps must be > 0"):
        build_walk_edges(
            stop_coords={"A": (53.55, 9.993), "B": (53.551, 9.993)},
            max_distance_m=200,
            walking_speed_mps=0.0,
            max_neighbors=4,
        )


def test_project_stops_preserves_all_stop_ids() -> None:
    projected = _project_stops(
        {
            "A": (53.5500, 9.9930),
            "B": (53.5510, 9.9940),
            "C": (53.5520, 9.9950),
        }
    )
    assert set(projected.keys()) == {"A", "B", "C"}
    assert projected["A"] != projected["B"]
