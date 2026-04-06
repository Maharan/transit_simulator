import type {
  RouteOptionResponse,
  RouteResponse,
} from '../types/route.types'

function countRideLegs(routeResult: RouteResponse): number {
  return routeResult.itinerary.legs.filter((leg) => leg.mode === 'ride').length
}

function getRouteOptions(routeResult: RouteResponse | null): RouteOptionResponse[] {
  if (!routeResult) {
    return []
  }

  if (routeResult.options.length > 0) {
    return routeResult.options
  }

  const transitLegs = countRideLegs(routeResult)
  return [
    {
      best_plan: routeResult.best_plan,
      itinerary: routeResult.itinerary,
      major_trip_transfers: Math.max(transitLegs - 1, 0),
      transit_legs: transitLegs,
    },
  ]
}

function getBestRouteOptionIndex(routeResult: RouteResponse | null): number {
  const options = getRouteOptions(routeResult)
  if (options.length === 0) {
    return 0
  }
  const requestedIndex = routeResult?.best_option_index ?? 0
  if (requestedIndex < 0 || requestedIndex >= options.length) {
    return 0
  }
  return requestedIndex
}

function getSelectedRouteOption(
  routeResult: RouteResponse | null,
  selectedOptionIndex: number | null,
): RouteOptionResponse | null {
  const options = getRouteOptions(routeResult)
  if (options.length === 0) {
    return null
  }

  const fallbackIndex = getBestRouteOptionIndex(routeResult)
  const normalizedIndex =
    selectedOptionIndex === null ||
    selectedOptionIndex < 0 ||
    selectedOptionIndex >= options.length
      ? fallbackIndex
      : selectedOptionIndex

  return options[normalizedIndex] ?? options[fallbackIndex] ?? null
}

export {
  getBestRouteOptionIndex,
  getRouteOptions,
  getSelectedRouteOption,
}
