import type { SelectedCoordinatePoint } from '../types/coordinates.types'
import type { PathSegmentResponse, RouteResponse } from '../types/route.types'
import { getSelectedRouteOption } from './routeOptions'

type LngLat = [number, number]

type LineGeometry = {
  type: 'LineString'
  coordinates: LngLat[]
}

type PointGeometry = {
  type: 'Point'
  coordinates: LngLat
}

type Geometry = LineGeometry | PointGeometry

type FeaturePropertyValue = string | number | boolean | null

type Feature<TGeometry extends Geometry = Geometry> = {
  type: 'Feature'
  properties: Record<string, FeaturePropertyValue>
  geometry: TGeometry
}

type FeatureCollection<TGeometry extends Geometry = Geometry> = {
  type: 'FeatureCollection'
  features: Feature<TGeometry>[]
}

type RouteMapData = {
  lineCollection: FeatureCollection<LineGeometry>
  stopCollection: FeatureCollection<PointGeometry>
  endpointCollection: FeatureCollection<PointGeometry>
  bounds: [LngLat, LngLat] | null
  shouldAutoFit: boolean
}

const TRANSIT_LEG_COLORS = [
  '#005AAE',
  '#E85D04',
  '#0F766E',
  '#B91C1C',
  '#7C3AED',
  '#CA8A04',
  '#0891B2',
  '#BE123C',
] as const

function isLngLatPoint(value: unknown): value is LngLat {
  if (!Array.isArray(value) || value.length < 2) {
    return false
  }
  const lon = value[0]
  const lat = value[1]
  return (
    typeof lon === 'number' &&
    Number.isFinite(lon) &&
    typeof lat === 'number' &&
    Number.isFinite(lat)
  )
}

function stopToPoint(stop: {
  stop_lon: number | null
  stop_lat: number | null
}): LngLat | null {
  if (
    typeof stop.stop_lon !== 'number' ||
    !Number.isFinite(stop.stop_lon) ||
    typeof stop.stop_lat !== 'number' ||
    !Number.isFinite(stop.stop_lat)
  ) {
    return null
  }
  return [stop.stop_lon, stop.stop_lat]
}

type BoundsTracker = {
  hasPoint: boolean
  minLon: number
  maxLon: number
  minLat: number
  maxLat: number
}

function createBoundsTracker(): BoundsTracker {
  return {
    hasPoint: false,
    minLon: 0,
    maxLon: 0,
    minLat: 0,
    maxLat: 0,
  }
}

function extendBounds(tracker: BoundsTracker, point: LngLat): void {
  const [lon, lat] = point
  if (!tracker.hasPoint) {
    tracker.hasPoint = true
    tracker.minLon = lon
    tracker.maxLon = lon
    tracker.minLat = lat
    tracker.maxLat = lat
    return
  }

  tracker.minLon = Math.min(tracker.minLon, lon)
  tracker.maxLon = Math.max(tracker.maxLon, lon)
  tracker.minLat = Math.min(tracker.minLat, lat)
  tracker.maxLat = Math.max(tracker.maxLat, lat)
}

function finalizeBounds(tracker: BoundsTracker): [LngLat, LngLat] | null {
  if (!tracker.hasPoint) {
    return null
  }

  return [
    [tracker.minLon, tracker.minLat],
    [tracker.maxLon, tracker.maxLat],
  ]
}

function normalizeHexColor(value: string | null | undefined): string | null {
  if (!value) {
    return null
  }
  const normalized = value.trim().toUpperCase()
  if (!/^#[0-9A-F]{6}$/.test(normalized)) {
    return null
  }
  return normalized
}

function transitLegKey(segment: PathSegmentResponse): string {
  return (
    segment.edge.trip_id ??
    segment.edge.route_id ??
    segment.edge.route ??
    `${segment.from_stop.stop_id}:${segment.to_stop.stop_id}`
  )
}

function pickTransitLegColor({
  preferredColor,
  transitLegIndex,
  previousTransitLegColor,
}: {
  preferredColor: string | null
  transitLegIndex: number
  previousTransitLegColor: string | null
}): string {
  const paletteColor =
    TRANSIT_LEG_COLORS[transitLegIndex % TRANSIT_LEG_COLORS.length]

  if (
    preferredColor &&
    preferredColor !== previousTransitLegColor
  ) {
    return preferredColor
  }

  if (paletteColor !== previousTransitLegColor) {
    return paletteColor
  }

  return TRANSIT_LEG_COLORS[
    (transitLegIndex + 1) % TRANSIT_LEG_COLORS.length
  ]
}

function buildRouteMapData(
  routeResult: RouteResponse | null,
  {
    selectedRouteOptionIndex = null,
    selectedFromPoint = null,
    selectedToPoint = null,
  }: {
    selectedRouteOptionIndex?: number | null
    selectedFromPoint?: SelectedCoordinatePoint | null
    selectedToPoint?: SelectedCoordinatePoint | null
  } = {},
): RouteMapData {
  const lineCollection: FeatureCollection<LineGeometry> = {
    type: 'FeatureCollection',
    features: [],
  }
  const stopCollection: FeatureCollection<PointGeometry> = {
    type: 'FeatureCollection',
    features: [],
  }
  const endpointCollection: FeatureCollection<PointGeometry> = {
    type: 'FeatureCollection',
    features: [],
  }
  const boundsTracker = createBoundsTracker()

  if (!routeResult) {
    if (selectedFromPoint) {
      const point: LngLat = [selectedFromPoint.lon, selectedFromPoint.lat]
      endpointCollection.features.push({
        type: 'Feature',
        properties: {
          endpointRole: 'start',
          stopName: 'Selected origin',
        },
        geometry: {
          type: 'Point',
          coordinates: point,
        },
      })
      extendBounds(boundsTracker, point)
    }

    if (selectedToPoint) {
      const point: LngLat = [selectedToPoint.lon, selectedToPoint.lat]
      endpointCollection.features.push({
        type: 'Feature',
        properties: {
          endpointRole: 'end',
          stopName: 'Selected destination',
        },
        geometry: {
          type: 'Point',
          coordinates: point,
        },
      })
      extendBounds(boundsTracker, point)
    }

    return {
      lineCollection,
      stopCollection,
      endpointCollection,
      bounds: finalizeBounds(boundsTracker),
      shouldAutoFit: false,
    }
  }

  const selectedRouteOption = getSelectedRouteOption(
    routeResult,
    selectedRouteOptionIndex,
  )
  if (!selectedRouteOption) {
    return {
      lineCollection,
      stopCollection,
      endpointCollection,
      bounds: finalizeBounds(boundsTracker),
      shouldAutoFit: false,
    }
  }

  let currentTransitLegKey: string | null = null
  let currentTransitLegColor: string | null = null
  let previousTransitLegColor: string | null = null
  let transitLegIndex = -1

  for (const segment of selectedRouteOption.itinerary.path_segments) {
    let coordinates: LngLat[] = []
    if (Array.isArray(segment.geometry)) {
      coordinates = segment.geometry.filter(isLngLatPoint)
    }
    if (coordinates.length < 2) {
      const fromPoint = stopToPoint(segment.from_stop)
      const toPoint = stopToPoint(segment.to_stop)
      if (fromPoint && toPoint) {
        coordinates = [fromPoint, toPoint]
      }
    }
    if (coordinates.length < 2) {
      continue
    }

    const isTransitSegment =
      segment.edge.kind === 'trip' || segment.edge.kind === 'ride'
    let lineColor: string | null = null
    let segmentTransitLegIndex: number | null = null

    if (isTransitSegment) {
      const nextTransitLegKey = transitLegKey(segment)
      if (nextTransitLegKey !== currentTransitLegKey) {
        transitLegIndex += 1
        currentTransitLegKey = nextTransitLegKey
        currentTransitLegColor = pickTransitLegColor({
          preferredColor: normalizeHexColor(segment.edge.display_color),
          transitLegIndex,
          previousTransitLegColor,
        })
        previousTransitLegColor = currentTransitLegColor
      }
      lineColor = currentTransitLegColor
      segmentTransitLegIndex = transitLegIndex
    } else {
      currentTransitLegKey = null
      currentTransitLegColor = null
    }

    lineCollection.features.push({
      type: 'Feature',
      properties: {
        edgeKind: segment.edge.kind,
        edgeLabel: segment.edge.label ?? '',
        lineColor,
        transitLegIndex: segmentTransitLegIndex,
        routeId: segment.edge.route_id ?? '',
        routeShortName: segment.edge.route ?? '',
      },
      geometry: {
        type: 'LineString',
        coordinates,
      },
    })
    for (const coordinate of coordinates) {
      extendBounds(boundsTracker, coordinate)
    }
  }

  for (const stop of selectedRouteOption.itinerary.stops) {
    const point = stopToPoint(stop)
    if (!point) {
      continue
    }
    stopCollection.features.push({
      type: 'Feature',
      properties: {
        stopName: stop.stop_name,
        stopId: stop.stop_id,
      },
      geometry: {
        type: 'Point',
        coordinates: point,
      },
    })
    extendBounds(boundsTracker, point)
  }

  const firstStop = selectedRouteOption.itinerary.stops[0]
  const lastStop =
    selectedRouteOption.itinerary.stops[
      selectedRouteOption.itinerary.stops.length - 1
    ]
  const firstPoint = selectedFromPoint
    ? ([selectedFromPoint.lon, selectedFromPoint.lat] as LngLat)
    : firstStop
      ? stopToPoint(firstStop)
      : null
  const lastPoint = selectedToPoint
    ? ([selectedToPoint.lon, selectedToPoint.lat] as LngLat)
    : lastStop
      ? stopToPoint(lastStop)
      : null

  if (firstPoint) {
    endpointCollection.features.push({
      type: 'Feature',
      properties: {
        endpointRole: 'start',
        stopName: selectedFromPoint ? 'Selected origin' : (firstStop?.stop_name ?? 'Start'),
      },
      geometry: {
        type: 'Point',
        coordinates: firstPoint,
      },
    })
    extendBounds(boundsTracker, firstPoint)
  }
  if (lastPoint) {
    endpointCollection.features.push({
      type: 'Feature',
      properties: {
        endpointRole: 'end',
        stopName: selectedToPoint ? 'Selected destination' : (lastStop?.stop_name ?? 'End'),
      },
      geometry: {
        type: 'Point',
        coordinates: lastPoint,
      },
    })
    extendBounds(boundsTracker, lastPoint)
  }

  return {
    lineCollection,
    stopCollection,
    endpointCollection,
    bounds: finalizeBounds(boundsTracker),
    shouldAutoFit: true,
  }
}

export { buildRouteMapData }
