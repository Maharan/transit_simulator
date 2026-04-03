import type {
  FloorSpaceDensityFeatureCollection,
  FloorSpaceDensityRequest,
} from '../types/floorSpace.types'


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

async function fetchFloorSpaceDensity(
  payload: FloorSpaceDensityRequest,
  signal?: AbortSignal,
): Promise<FloorSpaceDensityFeatureCollection> {
  const params = new URLSearchParams({
    dataset_release: payload.dataset_release,
    grid_resolution_m: String(payload.grid_resolution_m),
    min_lat: String(payload.min_lat),
    min_lon: String(payload.min_lon),
    max_lat: String(payload.max_lat),
    max_lon: String(payload.max_lon),
  })

  const response = await fetch(`/api/floor-space-density?${params.toString()}`, {
    method: 'GET',
    signal,
  })

  if (!response.ok) {
    const errorPayload = await parseJsonResponse<{ detail?: string }>(response)
    const detail =
      errorPayload?.detail ||
      `Floor-space density request failed with status ${response.status}`
    throw new Error(detail)
  }

  const data = await parseJsonResponse<FloorSpaceDensityFeatureCollection>(response)
  if (!data) {
    throw new Error(
      'Floor-space density request succeeded but returned an empty response body.',
    )
  }

  return data
}

export { fetchFloorSpaceDensity }
