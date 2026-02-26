export type Coordinate = {
  lat: number
  lon: number
}

export type ItineraryStop = {
  stop_id: string
  stop_name: string
  stop_lat: number | null | undefined
  stop_lon: number | null | undefined
}

export type ItineraryStopWithCoordinates = ItineraryStop & {
  stop_lat: number
  stop_lon: number
}

export type PathSegmentEdge = {
  kind: string
  label: string | null
  route: string | null
  route_id: string | null
  trip_id: string | null
  weight_sec: number | null
}

export type PathSegment = {
  from_stop: ItineraryStop
  to_stop: ItineraryStop
  edge: PathSegmentEdge
  geometry?: number[][] | null
}

export type ItineraryLeg = {
  mode: string
  from_stop: string | null
  to_stop: string | null
  route: string | null
  duration_sec: number | null
  text: string
}

export type RouteResponse = {
  context_lines: string[]
  itinerary: {
    summary: string
    timing: string
    stops: ItineraryStop[]
    path_segments: PathSegment[]
    legs: ItineraryLeg[]
  }
}

export type SegmentProperties = {
  segment_index: number
  leg_index: number
  color: string
  label: string
  leg_label: string
  style: 'solid' | 'walk'
}

export type StopProperties = {
  stop_id: string
  stop_name: string
  role: 'origin' | 'destination' | 'stop'
}
