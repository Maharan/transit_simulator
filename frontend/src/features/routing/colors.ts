import type { ItineraryLeg, PathSegmentEdge, StopProperties } from './types'

const ORIGIN_STOP_ID = '__coord_origin__'
const DESTINATION_STOP_ID = '__coord_destination__'

const RIDE_COLORS = [
  '#004c6d',
  '#2f4b7c',
  '#665191',
  '#a05195',
  '#d45087',
  '#f95d6a',
  '#ff7c43',
  '#ffa600',
]

function hashCode(value: string): number {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index)
    hash |= 0
  }
  return Math.abs(hash)
}

function rideColor(seed: string): string {
  return RIDE_COLORS[hashCode(seed) % RIDE_COLORS.length]
}

export function segmentColor(edge: PathSegmentEdge, fallbackSeed: string): string {
  if (edge.kind === 'trip') {
    const routeKey = edge.route ?? edge.route_id ?? edge.trip_id ?? fallbackSeed
    return rideColor(routeKey)
  }
  if (edge.label === 'walk') {
    return '#15803d'
  }
  if (edge.label === 'station_link') {
    return '#b45309'
  }
  return '#7c2d12'
}

export function legColor(leg: ItineraryLeg, index: number): string {
  if (leg.mode === 'ride') {
    return rideColor(leg.route ?? `ride-${index}`)
  }
  if (leg.mode === 'walk') {
    return '#15803d'
  }
  if (leg.mode === 'station_link') {
    return '#b45309'
  }
  return '#7c2d12'
}

export function stopRole(stopId: string): StopProperties['role'] {
  if (stopId === ORIGIN_STOP_ID) {
    return 'origin'
  }
  if (stopId === DESTINATION_STOP_ID) {
    return 'destination'
  }
  return 'stop'
}
