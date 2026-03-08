import { useCallback, useEffect, useRef, useState } from 'react'

import { postRoute } from './routeApi'
import type { RouteRequestPayload, RouteResponse } from '../types/route.types'
import { RouteApiError, isAbortError } from '../types/routeErrors.types'

function useRouteRequest() {
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [routeResult, setRouteResult] = useState<RouteResponse | null>(null)
  const routeRequestAbortRef = useRef<AbortController | null>(null)
  const submitRoute = useCallback(async (payload: RouteRequestPayload): Promise<void> => {
    routeRequestAbortRef.current?.abort()
    const controller = new AbortController()
    routeRequestAbortRef.current = controller

    setIsLoading(true)
    setErrorMessage(null)


    try {
      const result = await postRoute(payload, controller.signal)
      setRouteResult(result)

    } catch (error) {
      if (isAbortError(error)) {
        return
      }
      if (error instanceof RouteApiError) {
        setErrorMessage(error.detail)
        return
      }
      setErrorMessage('Unexpected error while requesting route.')
    } finally {
      if (routeRequestAbortRef.current === controller) {
        routeRequestAbortRef.current = null
        setIsLoading(false)
      }
    }
  }, [])

  const resetRouteRequest = useCallback((): void => {
    routeRequestAbortRef.current?.abort()
    routeRequestAbortRef.current = null

    setIsLoading(false)
    setErrorMessage(null)
    setRouteResult(null)
  }, [])

  useEffect(() => {
    return () => {
      routeRequestAbortRef.current?.abort()
      routeRequestAbortRef.current = null
    }
  }, [])

  return {
    isLoading,
    errorMessage,
    routeResult,
    submitRoute,
    resetRouteRequest,
  }
}

export { useRouteRequest }
