import type { LngLatBoundsLike } from 'maplibre-gl'

export const HAMBURG_CENTER: [number, number] = [9.9937, 53.5511]

export const HAMBURG_BOUNDS = {
  minLon: 8.0,
  minLat: 52.8,
  maxLon: 10.8,
  maxLat: 54.2,
} as const

export const HAMBURG_MAP_BOUNDS: LngLatBoundsLike = [
  [HAMBURG_BOUNDS.minLon, HAMBURG_BOUNDS.minLat],
  [HAMBURG_BOUNDS.maxLon, HAMBURG_BOUNDS.maxLat],
]
