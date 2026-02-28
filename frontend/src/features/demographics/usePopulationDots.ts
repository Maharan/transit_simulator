import { startTransition, useEffect, useMemo, useRef, useState } from 'react'

import {
  EMPTY_POPULATION_DOTS,
  type PopulationDotFeatureCollection,
  type PopulationGridCellFeatureCollection,
} from './types'

type PopulationDotsResponse = {
  requestId: number
  populationDots?: PopulationDotFeatureCollection
  errorMessage?: string
}

let nextPopulationDotsRequestId = 1

function allocatePopulationDotsRequestId(): number {
  const requestId = nextPopulationDotsRequestId
  nextPopulationDotsRequestId += 1
  return requestId
}

export function usePopulationDots(
  populationGrid: PopulationGridCellFeatureCollection | null,
  enabled: boolean
) {
  const workerRef = useRef<Worker | null>(null)
  const latestRequestIdRef = useRef(0)
  const requestId = useMemo(
    () => (populationGrid ? allocatePopulationDotsRequestId() : 0),
    [populationGrid]
  )

  const [completedRequestId, setCompletedRequestId] = useState(0)
  const [populationDots, setPopulationDots] =
    useState<PopulationDotFeatureCollection>(EMPTY_POPULATION_DOTS)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    const worker = new Worker(
      new URL('./populationDots.worker.ts', import.meta.url),
      { type: 'module' }
    )

    worker.onmessage = (event: MessageEvent<PopulationDotsResponse>) => {
      const { requestId: completedId, populationDots: nextPopulationDots, errorMessage: nextError } =
        event.data
      if (completedId !== latestRequestIdRef.current) {
        return
      }

      startTransition(() => {
        if (nextError) {
          setErrorMessage(nextError)
          setPopulationDots(EMPTY_POPULATION_DOTS)
        } else if (nextPopulationDots) {
          setErrorMessage(null)
          setPopulationDots(nextPopulationDots)
        }
        setCompletedRequestId(completedId)
      })
    }

    workerRef.current = worker

    return () => {
      worker.terminate()
      workerRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!enabled || !populationGrid || !workerRef.current) {
      return
    }
    if (completedRequestId === requestId) {
      return
    }

    latestRequestIdRef.current = requestId
    workerRef.current.postMessage({
      requestId,
      populationGrid,
    })
  }, [completedRequestId, enabled, populationGrid, requestId])

  return {
    populationDots: enabled && populationGrid ? populationDots : EMPTY_POPULATION_DOTS,
    isPreparing:
      enabled &&
      populationGrid !== null &&
      completedRequestId !== requestId,
    errorMessage,
  }
}
