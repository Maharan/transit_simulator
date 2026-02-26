import { useCallback, useEffect, useRef, useState } from 'react'

import type { Coordinate, RouteResponse } from './types'

type RouteErrorPayload = {
  detail?: string
}

function normalizeDepartTime(value: string | undefined): string | null {
  if (!value) {
    return null
  }
  const trimmed = value.trim()
  if (/^\d{2}:\d{2}$/.test(trimmed)) {
    return `${trimmed}:00`
  }
  if (/^\d{2}:\d{2}:\d{2}$/.test(trimmed)) {
    return trimmed
  }
  return null
}

export function useRouterRoute() {
  const requestControllerRef = useRef<AbortController | null>(null)

  const [route, setRoute] = useState<RouteResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const cancelRequest = useCallback(() => {
    requestControllerRef.current?.abort()
    requestControllerRef.current = null
    setIsLoading(false)
  }, [])

  useEffect(() => () => cancelRequest(), [cancelRequest])

  const clearRoute = useCallback(() => {
    setRoute(null)
  }, [])

  const clearError = useCallback(() => {
    setErrorMessage(null)
  }, [])

  const requestRoute = useCallback(
    async (from: Coordinate, to: Coordinate, departureTime?: string) => {
      requestControllerRef.current?.abort()
      const controller = new AbortController()
      requestControllerRef.current = controller

      setIsLoading(true)
      setErrorMessage(null)

      const payload: Record<string, number | string> = {
        from_lat: from.lat,
        from_lon: from.lon,
        to_lat: to.lat,
        to_lon: to.lon,
      }
      const normalizedDepartTime = normalizeDepartTime(departureTime)
      if (normalizedDepartTime) {
        payload.depart_time = normalizedDepartTime
      }

      try {
        const response = await fetch('/api/route', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          signal: controller.signal,
        })

        if (!response.ok) {
          const errorPayload = (await response.json().catch(() => null)) as
            | RouteErrorPayload
            | null
          throw new Error(
            errorPayload?.detail ?? `Router request failed (${response.status})`
          )
        }

        const routePayload = (await response.json()) as RouteResponse
        setRoute(routePayload)
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }
        setRoute(null)
        setErrorMessage(error instanceof Error ? error.message : 'Unknown router error')
      } finally {
        if (requestControllerRef.current === controller) {
          requestControllerRef.current = null
          setIsLoading(false)
        }
      }
    },
    []
  )

  return {
    route,
    isLoading,
    errorMessage,
    requestRoute,
    cancelRequest,
    clearRoute,
    clearError,
  }
}
