import { buildPopulationDotFeatureCollection } from './dotDensity'
import type {
  PopulationDotFeatureCollection,
  PopulationGridCellFeatureCollection,
} from './types'

type PopulationDotsRequest = {
  requestId: number
  populationGrid: PopulationGridCellFeatureCollection
}

type PopulationDotsResponse = {
  requestId: number
  populationDots?: PopulationDotFeatureCollection
  errorMessage?: string
}

self.onmessage = (event: MessageEvent<PopulationDotsRequest>) => {
  const { requestId, populationGrid } = event.data

  try {
    const populationDots = buildPopulationDotFeatureCollection(populationGrid)
    const response: PopulationDotsResponse = {
      requestId,
      populationDots,
    }
    self.postMessage(response)
  } catch (error) {
    const response: PopulationDotsResponse = {
      requestId,
      errorMessage:
        error instanceof Error ? error.message : 'Population dot worker failed',
    }
    self.postMessage(response)
  }
}

export {}
