from __future__ import annotations

from core.graph.build import Graph, TripBucket, _add_walk_edges
from core.graph.lite import GraphLite
from core.routing.td_dijkstra import td_dijkstra
from core.routing.utils import parse_time_to_seconds


def test_walk_edges_flow_from_graph_to_lite_to_dijkstra() -> None:
    graph = Graph()
    graph.add_node("A", 53.5500, 9.9930)
    graph.add_node("B", 53.5510, 9.9930)

    added_count = _add_walk_edges(
        graph=graph,
        stop_coords={
            "A": (53.5500, 9.9930),
            "B": (53.5510, 9.9930),
        },
        walk_max_distance_m=250,
        walk_speed_mps=1.2,
        walk_max_neighbors=4,
    )
    assert added_count >= 1

    lite = GraphLite.from_graph(graph)
    result = td_dijkstra(
        graph=lite,
        start_id="A",
        goal_id="B",
        depart_time_str="09:00:00",
    )

    assert result.arrival_time_sec is not None
    assert result.edge_path
    assert result.edge_path[0].label == "walk"
    assert result.arrival_time_sec > parse_time_to_seconds("09:00:00")


def test_trip_bucket_ids_survive_lite_compression_and_resolution() -> None:
    graph = Graph()
    graph.trip_buckets["A"].append(
        TripBucket(
            to_stop_id="B",
            dep_secs=[9 * 3600],
            arr_secs=[9 * 3600 + 180],
            trip_ids=["trip-42"],
            route_ids=["route-7"],
            last_dep=9 * 3600,
        )
    )

    lite = GraphLite.from_graph(graph)
    result = td_dijkstra(
        graph=lite,
        start_id="A",
        goal_id="B",
        depart_time_str="08:55:00",
        state_by="route",
    )

    assert result.arrival_time_sec == 9 * 3600 + 180
    assert len(result.edge_path) == 1
    edge = result.edge_path[0]
    assert edge.kind == "trip"
    assert edge.trip_id == "trip-42"
    assert edge.route_id == "route-7"
    assert edge.dep_time == "09:00:00"
    assert edge.arr_time == "09:03:00"
