type RouteRequestPayload = {
  from_lat: number
  from_lon: number
  to_lat: number
  to_lon: number
  depart_time?: string
  graph_method?: string
  max_major_transfers?: number
}

type EndpointCandidateResponse = {
  stop_id: string
  stop_name: string
  parent_id: string
  parent_name: string
  walk_distance_m: number
  walk_time_sec: number
}

type ItineraryEdgeResponse = {
  to_stop_id: string
  weight_sec: number | null
  kind: string
  trip_id: string | null
  route_id: string | null
  service_id: string | null
  dep_time: string | null
  arr_time: string | null
  dep_time_sec: number | null
  arr_time_sec: number | null
  transfer_type: number | null
  stop_sequence: number | null
  apply_penalty: boolean | null
  label: string | null
}

type TransitPathResponse = {
  arrival_time_sec: number | null
  stop_path: string[]
  edge_path: ItineraryEdgeResponse[]
}

type RoutePlanResponse = {
  from_candidate: EndpointCandidateResponse
  to_candidate: EndpointCandidateResponse
  transit_result: TransitPathResponse
  transit_depart_time_sec: number
  arrival_time_sec: number
}

type LegResponse = {
  mode: string
  from_stop: string | null
  to_stop: string | null
  route: string | null
  duration_sec: number | null
  duration_min: number | null
  text: string
}

type StopResponse = {
  stop_id: string
  stop_name: string
  stop_lat: number | null
  stop_lon: number | null
}

type PathSegmentEdgeResponse = {
  kind: string
  label: string | null
  weight_sec: number | null
  route: string | null
  route_id: string | null
  display_color: string | null
  display_text_color: string | null
  trip_id: string | null
  dep_time: string | null
  arr_time: string | null
  dep_time_sec: number | null
  arr_time_sec: number | null
  transfer_type: number | null
  apply_penalty: boolean
}

type PathSegmentResponse = {
  from_stop: StopResponse
  to_stop: StopResponse
  edge: PathSegmentEdgeResponse
  geometry: number[][] | null
}

type ItineraryResponse = {
  summary: string
  timing: string
  stops: StopResponse[]
  path_segments: PathSegmentResponse[]
  legs: LegResponse[]
}

type RouteOptionResponse = {
  best_plan: RoutePlanResponse
  itinerary: ItineraryResponse
  major_trip_transfers: number
  transit_legs: number
}

type RouteResponse = {
  feed_id: string
  cache_logs: string[]
  context_lines: string[]
  itinerary: ItineraryResponse
  best_plan: RoutePlanResponse
  options: RouteOptionResponse[]
  best_option_index: number
}

type RouteErrorResponse = {
  detail: string
}

export type {
  RouteRequestPayload,
  RouteResponse,
  RouteErrorResponse,
  EndpointCandidateResponse,
  ItineraryEdgeResponse,
  TransitPathResponse,
  RoutePlanResponse,
  LegResponse,
  StopResponse,
  PathSegmentEdgeResponse,
  PathSegmentResponse,
  ItineraryResponse,
  RouteOptionResponse,
}
