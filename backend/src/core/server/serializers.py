from __future__ import annotations

from typing import Literal

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
    stop_lat: float | None = None
    stop_lon: float | None = None


class PathSegmentEdgeResponse(BaseModel):
    kind: str
    label: str | None = None
    weight_sec: int | None = None
    route: str | None = None
    route_id: str | None = None
    display_color: str | None = None
    display_text_color: str | None = None
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
    geometry: list[list[float]] | None = None


class ItineraryResponse(BaseModel):
    summary: str
    timing: str
    stops: list[StopResponse]
    path_segments: list[PathSegmentResponse]
    legs: list[LegResponse]


class RouteOptionResponse(BaseModel):
    best_plan: RoutePlanResponse
    itinerary: ItineraryResponse
    major_trip_transfers: int
    transit_legs: int


class RouteResponse(BaseModel):
    feed_id: str
    cache_logs: list[str]
    context_lines: list[str]
    itinerary: ItineraryResponse
    best_plan: RoutePlanResponse
    options: list[RouteOptionResponse] = []
    best_option_index: int = 0


class ReloadGraphResponse(BaseModel):
    cache_logs: list[str]


class NetworkLineGeometryResponse(BaseModel):
    type: Literal["LineString", "MultiLineString"]
    coordinates: list[list[float]] | list[list[list[float]]]


class NetworkLinePropertiesResponse(BaseModel):
    line_id: str
    line_family: str
    color: str
    offset_px: float = 0.0


class NetworkLineFeatureResponse(BaseModel):
    type: Literal["Feature"] = "Feature"
    properties: NetworkLinePropertiesResponse
    geometry: NetworkLineGeometryResponse


class NetworkLineFeatureCollectionResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[NetworkLineFeatureResponse]


class PopulationGridGeometryResponse(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[list[float]]]


class PopulationGridPropertiesResponse(BaseModel):
    population_estimate: float


class PopulationGridFeatureResponse(BaseModel):
    type: Literal["Feature"] = "Feature"
    properties: PopulationGridPropertiesResponse
    geometry: PopulationGridGeometryResponse


class PopulationGridFeatureCollectionResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[PopulationGridFeatureResponse]


class FloorSpaceDensityGeometryResponse(BaseModel):
    type: Literal["Point"]
    coordinates: list[float]


class FloorSpaceDensityPropertiesResponse(BaseModel):
    building_count: int
    floor_space_m2: float
    floor_space_density_sqkm: float
    population_estimate: float
    population_density_sqkm: float


class FloorSpaceDensityFeatureResponse(BaseModel):
    type: Literal["Feature"] = "Feature"
    properties: FloorSpaceDensityPropertiesResponse
    geometry: FloorSpaceDensityGeometryResponse


class FloorSpaceDensityFeatureCollectionResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[FloorSpaceDensityFeatureResponse]


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
    max_wait_sec: int | None = None
    max_rounds: int | None = None
    max_major_transfers: int | None = None
    heuristic_max_speed_mps: float | None = None
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
