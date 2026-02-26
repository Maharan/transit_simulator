import { useCallback, useEffect, useRef, useState } from 'react'

import type { NetworkLineFeatureCollection } from './types'

type NetworkLineErrorPayload = {
  detail?: string
}

export function useNetworkLines() {
  const requestControllerRef = useRef<AbortController | null>(null)

  const [networkLines, setNetworkLines] = useState<NetworkLineFeatureCollection | null>(
    null
  )
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const loadNetworkLines = useCallback(async () => {
    requestControllerRef.current?.abort()
    const controller = new AbortController()
    requestControllerRef.current = controller

    setIsLoading(true)
    setErrorMessage(null)

    try {
      const response = await fetch('/api/network-lines', {
        method: 'GET',
        signal: controller.signal,
      })
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | NetworkLineErrorPayload
          | null
        throw new Error(payload?.detail ?? `Network line fetch failed (${response.status})`)
      }
      const payload = (await response.json()) as NetworkLineFeatureCollection
      setNetworkLines(payload)
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      setNetworkLines(null)
      setErrorMessage(error instanceof Error ? error.message : 'Unknown network line error')
    } finally {
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null
        setIsLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    return () => {
      requestControllerRef.current?.abort()
      requestControllerRef.current = null
    }
  }, [])

  return {
    networkLines,
    isLoading,
    errorMessage,
    loadNetworkLines,
  }
}
