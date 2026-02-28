import { startTransition, useCallback, useEffect, useRef, useState } from 'react'

import type {
  PopulationBounds,
  PopulationGridCellFeatureCollection,
} from './types'
import {
  getPopulationTileCoverageKey,
  getPopulationTilesForBounds,
  mergePopulationGridTiles,
} from './populationTiles'
import { HAMBURG_BOUNDS } from '../map/constants'

type PopulationHeatmapErrorPayload = {
  detail?: string
}

const POPULATION_TILE_CACHE_PREFIX = 'population-grid-tile-v1'

function buildTileStorageKey(datasetYear: number, tileKey: string): string {
  return `${POPULATION_TILE_CACHE_PREFIX}:${datasetYear}:${tileKey}`
}

function readTileFromSessionStorage(
  datasetYear: number,
  tileKey: string
): PopulationGridCellFeatureCollection | null {
  if (typeof window === 'undefined') {
    return null
  }

  try {
    const serialized = window.sessionStorage.getItem(
      buildTileStorageKey(datasetYear, tileKey)
    )
    if (!serialized) {
      return null
    }
    return JSON.parse(serialized) as PopulationGridCellFeatureCollection
  } catch {
    window.sessionStorage.removeItem(buildTileStorageKey(datasetYear, tileKey))
    return null
  }
}

function writeTileToSessionStorage(
  datasetYear: number,
  tileKey: string,
  collection: PopulationGridCellFeatureCollection
): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    window.sessionStorage.setItem(
      buildTileStorageKey(datasetYear, tileKey),
      JSON.stringify(collection)
    )
  } catch {
    // Ignore storage quota and serialization failures; the in-memory cache still works.
  }
}

export function usePopulationHeatmap() {
  const latestRequestIdRef = useRef(0)
  const activeTileCoverageKeyRef = useRef<string | null>(null)
  const tileCacheRef = useRef(new Map<string, PopulationGridCellFeatureCollection>())
  const inFlightTileRequestsRef = useRef(
    new Map<string, Promise<PopulationGridCellFeatureCollection>>()
  )

  const [populationHeatmap, setPopulationHeatmap] =
    useState<PopulationGridCellFeatureCollection | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const loadPopulationHeatmap = useCallback(
    async (bounds: PopulationBounds, datasetYear = 2020) => {
      const tiles = getPopulationTilesForBounds(bounds, HAMBURG_BOUNDS)
      if (tiles.length === 0) {
        setPopulationHeatmap(null)
        setIsLoading(false)
        return
      }

      const cachedTileCollections = tiles
        .map(({ key }) => {
          const tileStorageKey = buildTileStorageKey(datasetYear, key)
          const cachedCollection = tileCacheRef.current.get(tileStorageKey)
          if (cachedCollection) {
            return cachedCollection
          }

          const cachedInSession = readTileFromSessionStorage(datasetYear, key)
          if (cachedInSession) {
            tileCacheRef.current.set(tileStorageKey, cachedInSession)
            return cachedInSession
          }

          return null
        })
        .filter(
          (collection): collection is PopulationGridCellFeatureCollection =>
            collection !== null
        )

      const tileCoverageKey = getPopulationTileCoverageKey(bounds, HAMBURG_BOUNDS)
      if (
        tileCoverageKey === activeTileCoverageKeyRef.current &&
        cachedTileCollections.length === tiles.length
      ) {
        return
      }

      activeTileCoverageKeyRef.current = tileCoverageKey
      const requestId = latestRequestIdRef.current + 1
      latestRequestIdRef.current = requestId
      setErrorMessage(null)

      startTransition(() => {
        setPopulationHeatmap(mergePopulationGridTiles(cachedTileCollections))
      })

      const missingTiles = tiles.filter(
        ({ key }) => !tileCacheRef.current.has(buildTileStorageKey(datasetYear, key))
      )
      if (missingTiles.length === 0) {
        setIsLoading(false)
        return
      }

      setIsLoading(true)

      const tileResults = await Promise.allSettled(
        missingTiles.map(async ({ key, bounds: tileBounds }) => {
          const tileStorageKey = buildTileStorageKey(datasetYear, key)
          const existingRequest = inFlightTileRequestsRef.current.get(tileStorageKey)
          if (existingRequest) {
            return { key, collection: await existingRequest }
          }

          const tileRequest = (async () => {
            const searchParams = new URLSearchParams({
              dataset_year: String(datasetYear),
              min_lat: String(tileBounds.minLat),
              min_lon: String(tileBounds.minLon),
              max_lat: String(tileBounds.maxLat),
              max_lon: String(tileBounds.maxLon),
            })

            const response = await fetch(`/api/population-grid?${searchParams.toString()}`, {
              method: 'GET',
            })
            if (!response.ok) {
              const payload = (await response.json().catch(() => null)) as
                | PopulationHeatmapErrorPayload
                | null
              throw new Error(
                payload?.detail ?? `Population layer fetch failed (${response.status})`
              )
            }

            return (await response.json()) as PopulationGridCellFeatureCollection
          })()

          inFlightTileRequestsRef.current.set(tileStorageKey, tileRequest)

          try {
            const collection = await tileRequest
            tileCacheRef.current.set(tileStorageKey, collection)
            writeTileToSessionStorage(datasetYear, key, collection)
            return { key, collection }
          } finally {
            inFlightTileRequestsRef.current.delete(tileStorageKey)
          }
        })
      )

      if (latestRequestIdRef.current !== requestId) {
        return
      }

      const successfulCollections = tileResults
        .filter(
          (
            result
          ): result is PromiseFulfilledResult<{
            key: string
            collection: PopulationGridCellFeatureCollection
          }> => result.status === 'fulfilled'
        )
        .map((result) => result.value.collection)

      const failedTile = tileResults.find((result) => result.status === 'rejected')

      if (failedTile) {
        setErrorMessage(
          failedTile.reason instanceof Error
            ? failedTile.reason.message
            : 'Unknown population layer error'
        )
      }

      startTransition(() => {
        setPopulationHeatmap(
          mergePopulationGridTiles([...cachedTileCollections, ...successfulCollections])
        )
      })
      setIsLoading(false)
    },
    []
  )

  useEffect(() => {
    const inFlightTileRequests = inFlightTileRequestsRef.current

    return () => {
      inFlightTileRequests.clear()
    }
  }, [])

  return {
    populationHeatmap,
    isLoading,
    errorMessage,
    loadPopulationHeatmap,
  }
}
