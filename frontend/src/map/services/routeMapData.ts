import type { RouteResponse } from '../types/route.types'

type LngLat = [number, number]

type FeatureCollection = {
  type: 'FeatureCollection'
  features: Array<{
    type: 'Feature'
    properties: Record<string, string>
    geometry: {
      type: 'LineString' | 'Point'
      coordinates: LngLat[] | LngLat
    }
  }>
}

type RouteMapData = {
  lineCollection: FeatureCollection
  stopCollection: FeatureCollection
  endpointCollection: FeatureCollection
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

function computeBounds(points: LngLat[]): [LngLat, LngLat] | null {
  if (points.length === 0) {
    return null
  }

  let minLon = points[0][0]
  let maxLon = points[0][0]
  let minLat = points[0][1]
  let maxLat = points[0][1]

  for (const [lon, lat] of points) {
    minLon = Math.min(minLon, lon)
    maxLon = Math.max(maxLon, lon)
    minLat = Math.min(minLat, lat)
    maxLat = Math.max(maxLat, lat)
  }

  return [
    [minLon, minLat],
    [maxLon, maxLat],
  ]
}

function buildRouteMapData(routeResult: RouteResponse | null): RouteMapData {
  const lineCollection: FeatureCollection = {
    type: 'FeatureCollection',
    features: [],
  }
  const stopCollection: FeatureCollection = {
    type: 'FeatureCollection',
    features: [],
  }
  const endpointCollection: FeatureCollection = {
    type: 'FeatureCollection',
    features: [],
  }
  const boundsPoints: LngLat[] = []

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
    boundsPoints.push(...coordinates)
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
    boundsPoints.push(point)
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
    bounds: computeBounds(boundsPoints),
  }
}

export { buildRouteMapData }
