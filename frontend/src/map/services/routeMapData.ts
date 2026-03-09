import type { RouteResponse } from '../types/route.types'

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

type Feature<TGeometry extends Geometry = Geometry> = {
  type: 'Feature'
  properties: Record<string, string>
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
}

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

function buildRouteMapData(routeResult: RouteResponse | null): RouteMapData {
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
    return {
      lineCollection,
      stopCollection,
      endpointCollection,
      bounds: null,
    }
  }

  for (const segment of routeResult.itinerary.path_segments) {
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

    lineCollection.features.push({
      type: 'Feature',
      properties: {
        edgeKind: segment.edge.kind,
        edgeLabel: segment.edge.label ?? '',
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

  for (const stop of routeResult.itinerary.stops) {
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

  const firstStop = routeResult.itinerary.stops[0]
  const lastStop = routeResult.itinerary.stops[routeResult.itinerary.stops.length - 1]
  const firstPoint = firstStop ? stopToPoint(firstStop) : null
  const lastPoint = lastStop ? stopToPoint(lastStop) : null

  if (firstStop && firstPoint) {
    endpointCollection.features.push({
      type: 'Feature',
      properties: {
        endpointRole: 'start',
        stopName: firstStop.stop_name,
      },
      geometry: {
        type: 'Point',
        coordinates: firstPoint,
      },
    })
  }
  if (lastStop && lastPoint) {
    endpointCollection.features.push({
      type: 'Feature',
      properties: {
        endpointRole: 'end',
        stopName: lastStop.stop_name,
      },
      geometry: {
        type: 'Point',
        coordinates: lastPoint,
      },
    })
  }

  return {
    lineCollection,
    stopCollection,
    endpointCollection,
    bounds: finalizeBounds(boundsTracker),
  }
}

export { buildRouteMapData }
