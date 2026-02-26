import type { FeatureCollection, LineString, Point } from 'geojson'

import { segmentColor, stopRole } from './colors'
import type {
  ItineraryStop,
  ItineraryStopWithCoordinates,
  RouteResponse,
  SegmentProperties,
  StopProperties,
} from './types'

export const EMPTY_SEGMENTS: FeatureCollection<LineString, SegmentProperties> = {
  type: 'FeatureCollection',
  features: [],
}

export const EMPTY_STOPS: FeatureCollection<Point, StopProperties> = {
  type: 'FeatureCollection',
  features: [],
}

export function hasCoordinates(
  stop: ItineraryStop
): stop is ItineraryStopWithCoordinates {
  return typeof stop.stop_lat === 'number' && typeof stop.stop_lon === 'number'
}

export function buildSegmentFeatures(
  route: RouteResponse | null
): FeatureCollection<LineString, SegmentProperties> {
  if (!route) {
    return EMPTY_SEGMENTS
  }

  const legAssignments = buildLegAssignments(route)

  const features = route.itinerary.path_segments
    .map((segment, index) => {
      if (!hasCoordinates(segment.from_stop) || !hasCoordinates(segment.to_stop)) {
        return null
      }

      const labelParts = [
        segment.edge.kind,
        segment.edge.label ?? '',
        segment.edge.route ?? '',
        segment.edge.route_id ?? '',
      ].filter(Boolean)
      const shapedCoordinates =
        Array.isArray(segment.geometry) &&
        segment.geometry.length >= 2 &&
        segment.geometry.every(
          (point) =>
            Array.isArray(point) &&
            point.length >= 2 &&
            typeof point[0] === 'number' &&
            typeof point[1] === 'number'
        )
          ? segment.geometry.map((point) => [point[0], point[1]] as [number, number])
          : null
      const legAssignment = legAssignments[index]
      const legLabel =
        legAssignment?.leg_label && legAssignment.leg_label.length > 0
          ? legAssignment.leg_label
          : labelParts.join(' | ')
      const style: SegmentProperties['style'] =
        segment.edge.label === 'walk' ? 'walk' : 'solid'

      return {
        type: 'Feature' as const,
        properties: {
          segment_index: index,
          leg_index: legAssignment?.leg_index ?? index,
          color: segmentColor(segment.edge, `segment-${index}`),
          label: labelParts.join(' | '),
          leg_label: legLabel,
          style,
        },
        geometry: {
          type: 'LineString' as const,
          coordinates:
            shapedCoordinates ?? [
              [segment.from_stop.stop_lon, segment.from_stop.stop_lat],
              [segment.to_stop.stop_lon, segment.to_stop.stop_lat],
            ],
        },
      }
    })
    .filter((feature): feature is NonNullable<typeof feature> => feature !== null)

  return { type: 'FeatureCollection', features }
}

function buildLegAssignments(
  route: RouteResponse
): Array<{ leg_index: number; leg_label: string }> {
  const pathSegments = route.itinerary.path_segments
  const legs = route.itinerary.legs

  if (legs.length === 0) {
    return pathSegments.map((_, index) => ({
      leg_index: index,
      leg_label: `Segment ${index + 1}`,
    }))
  }

  let currentLegIndex = 0
  return pathSegments.map((segment) => {
    const safeLegIndex = Math.min(currentLegIndex, legs.length - 1)
    const currentLeg = legs[safeLegIndex]
    const legLabel = currentLeg?.text?.trim() || `Leg ${safeLegIndex + 1}`

    if (
      currentLeg &&
      typeof currentLeg.to_stop === 'string' &&
      segment.to_stop.stop_name === currentLeg.to_stop &&
      currentLegIndex < legs.length - 1
    ) {
      currentLegIndex += 1
    }

    return { leg_index: safeLegIndex, leg_label: legLabel }
  })
}

export function buildStopFeatures(
  route: RouteResponse | null
): FeatureCollection<Point, StopProperties> {
  if (!route) {
    return EMPTY_STOPS
  }

  const seen = new Set<string>()
  const features = route.itinerary.stops
    .map((stop) => {
      if (!hasCoordinates(stop)) {
        return null
      }

      const key = `${stop.stop_id}::${stop.stop_lat}::${stop.stop_lon}`
      if (seen.has(key)) {
        return null
      }
      seen.add(key)

      return {
        type: 'Feature' as const,
        properties: {
          stop_id: stop.stop_id,
          stop_name: stop.stop_name,
          role: stopRole(stop.stop_id),
        },
        geometry: {
          type: 'Point' as const,
          coordinates: [stop.stop_lon, stop.stop_lat],
        },
      }
    })
    .filter((feature): feature is NonNullable<typeof feature> => feature !== null)

  return { type: 'FeatureCollection', features }
}

export function hasAnyMissingSegmentCoordinates(route: RouteResponse | null): boolean {
  if (!route || route.itinerary.path_segments.length === 0) {
    return false
  }
  return route.itinerary.path_segments.some(
    (segment) =>
      !hasCoordinates(segment.from_stop) || !hasCoordinates(segment.to_stop)
  )
}
