from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    default_feed_id: str
    graph_cache_version: int
    default_graph_method: str | None = None


class EndpointCandidateResponse(BaseModel):
    stop_id: str
    stop_name: str
    parent_id: str
    parent_name: str
    walk_distance_m: float
    walk_time_sec: int


class ItineraryEdgeResponse(BaseModel):
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
    apply_penalty: bool | None = None
    label: str | None = None


class TransitPathResponse(BaseModel):
    arrival_time_sec: int | None
    stop_path: list[str]
    edge_path: list[ItineraryEdgeResponse]


class RoutePlanResponse(BaseModel):
    from_candidate: EndpointCandidateResponse
    to_candidate: EndpointCandidateResponse
    transit_result: TransitPathResponse
    transit_depart_time_sec: int
    arrival_time_sec: int


class LegResponse(BaseModel):
    mode: str
    from_stop: str | None = None
    to_stop: str | None = None
    route: str | None = None
    duration_sec: int | None = None
    duration_min: float | None = None
    text: str


class StopResponse(BaseModel):
    stop_id: str
    stop_name: str


class PathSegmentEdgeResponse(BaseModel):
    kind: str
    label: str | None = None
    weight_sec: int | None = None
    route: str | None = None
    route_id: str | None = None
    trip_id: str | None = None
    dep_time: str | None = None
    arr_time: str | None = None
    dep_time_sec: int | None = None
    arr_time_sec: int | None = None
    transfer_type: int | None = None
    apply_penalty: bool


class PathSegmentResponse(BaseModel):
    from_stop: StopResponse
    to_stop: StopResponse
    edge: PathSegmentEdgeResponse


class ItineraryResponse(BaseModel):
    summary: str
    timing: str
    stops: list[StopResponse]
    path_segments: list[PathSegmentResponse]
    legs: list[LegResponse]


class RouteResponse(BaseModel):
    feed_id: str
    cache_logs: list[str]
    context_lines: list[str]
    itinerary: ItineraryResponse
    best_plan: RoutePlanResponse


class ReloadGraphResponse(BaseModel):
    cache_logs: list[str]


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_stop_name: str | None = None
    to_stop_name: str | None = None
    from_stop_id: str | None = None
    to_stop_id: str | None = None
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    coord_max_candidates: int | None = None
    coord_max_distance_m: float | None = None
    feed_id: str | None = None
    rebuild: bool | None = None
    assume_zero_missing: bool | None = None
    depart_time: str | None = None
    transfer_penalty_sec: int | None = None
    route_change_penalty_sec: int | None = None
    state_by: str | None = None
    time_horizon_sec: int | None = None
    disable_walking: bool | None = None
    walk_max_distance_m: int | None = None
    walk_speed_mps: float | None = None
    walk_max_neighbors: int | None = None
    graph_cache_path: str | None = None
    rebuild_graph_cache: bool | None = None
    symmetric_transfers: bool | None = None
    graph_method: str | None = None
    anytime_default_headway_sec: int | None = None
    graph_cache_version: int | None = None


class ReloadGraphRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rebuild: bool = True
