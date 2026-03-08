import type {
  RouteErrorResponse,
  RouteRequestPayload,
  RouteResponse,
} from '../types/route.types'
import { RouteApiError } from '../types/routeErrors.types'


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

async function postRoute(
  payload: RouteRequestPayload,
  signal?: AbortSignal,
): Promise<RouteResponse> {
  const response = await fetch('/api/route', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })

  if (!response.ok) {
    const errorPayload = await parseJsonResponse<RouteErrorResponse>(response)
    const detail =
      errorPayload?.detail ||
      `Route request failed with status ${response.status}`
    throw new RouteApiError(response.status, detail)
  }

  const data = await parseJsonResponse<RouteResponse>(response)
  if (!data) {
    throw new RouteApiError(
      response.status,
      'Route request succeeded but returned an empty response body.',
    )
  }

  return data
}

export { postRoute }
