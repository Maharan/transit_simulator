import type {
  NetworkLineFeatureCollection,
  NetworkLineFamily,
} from '../types/networkLines.types'

const RAPID_TRANSIT_FAMILIES = new Set<NetworkLineFamily>(['u_bahn', 's_bahn'])

async function parseJsonResponse<T>(response: Response): Promise<T | null> {
  const text = await response.text()
  if (!text) {
    return null
  }

  try {
    return JSON.parse(text) as T
  } catch {
    return null
  }
}

function filterRapidTransitLines(
  featureCollection: NetworkLineFeatureCollection,
): NetworkLineFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: featureCollection.features.filter((feature) =>
      RAPID_TRANSIT_FAMILIES.has(feature.properties.line_family),
    ),
  }
}

async function fetchRapidTransitNetworkLines(
  signal?: AbortSignal,
): Promise<NetworkLineFeatureCollection> {
  const response = await fetch('/api/network-lines', {
    method: 'GET',
    signal,
  })

  if (!response.ok) {
    const errorPayload = await parseJsonResponse<{ detail?: string }>(response)
    const detail =
      errorPayload?.detail ||
      `Network line request failed with status ${response.status}`
    throw new Error(detail)
  }

  const data = await parseJsonResponse<NetworkLineFeatureCollection>(response)
  if (!data) {
    throw new Error(
      'Network line request succeeded but returned an empty response body.',
    )
  }

  return filterRapidTransitLines(data)
}

export { fetchRapidTransitNetworkLines }
