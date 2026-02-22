__all__ = [
    "EdgeLike",
    "EndpointCandidate",
    "GraphLike",
    "PathResult",
    "RoutePlan",
    "RoutePlannerRequest",
    "RoutePlannerResult",
    "ResultLike",
    "build_output_lines",
    "find_best_route_and_itinerary",
    "parse_time_to_seconds",
    "select_context_lines",
    "td_dijkstra",
]


def __getattr__(name: str):
    if name in {"EdgeLike", "GraphLike", "ResultLike"}:
        from .types import EdgeLike, GraphLike, ResultLike

        return {"EdgeLike": EdgeLike, "GraphLike": GraphLike, "ResultLike": ResultLike}[
            name
        ]
    if name in {"build_output_lines", "select_context_lines"}:
        from .output import build_output_lines, select_context_lines

        return {
            "build_output_lines": build_output_lines,
            "select_context_lines": select_context_lines,
        }[name]
    if name in {"PathResult", "td_dijkstra"}:
        from .td_dijkstra import PathResult, td_dijkstra

        return {"PathResult": PathResult, "td_dijkstra": td_dijkstra}[name]
    if name in {"parse_time_to_seconds"}:
        from .utils import parse_time_to_seconds

        return parse_time_to_seconds
    if name in {
        "EndpointCandidate",
        "RoutePlan",
        "RoutePlannerRequest",
        "RoutePlannerResult",
        "find_best_route_and_itinerary",
    }:
        from .route_planner import (
            EndpointCandidate,
            RoutePlan,
            RoutePlannerRequest,
            RoutePlannerResult,
            find_best_route_and_itinerary,
        )

        return {
            "EndpointCandidate": EndpointCandidate,
            "RoutePlan": RoutePlan,
            "RoutePlannerRequest": RoutePlannerRequest,
            "RoutePlannerResult": RoutePlannerResult,
            "find_best_route_and_itinerary": find_best_route_and_itinerary,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
