import {
  EMPTY_POPULATION_GRID,
  type PopulationBounds,
  type PopulationGridCellFeatureCollection,
} from './types.ts'

export const POPULATION_TILE_LAT_DEGREES = 0.2
export const POPULATION_TILE_LON_DEGREES = 0.2

export type PopulationTile = {
  key: string
  bounds: PopulationBounds
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum)
}

export function clampPopulationBounds(
  bounds: PopulationBounds,
  coverageBounds: PopulationBounds
): PopulationBounds | null {
  const minLat = clamp(bounds.minLat, coverageBounds.minLat, coverageBounds.maxLat)
  const minLon = clamp(bounds.minLon, coverageBounds.minLon, coverageBounds.maxLon)
  const maxLat = clamp(bounds.maxLat, coverageBounds.minLat, coverageBounds.maxLat)
  const maxLon = clamp(bounds.maxLon, coverageBounds.minLon, coverageBounds.maxLon)

  if (minLat >= maxLat || minLon >= maxLon) {
    return null
  }

  return {
    minLat,
    minLon,
    maxLat,
    maxLon,
  }
}

function buildPopulationTileKey(tileX: number, tileY: number): string {
  return `${tileX}:${tileY}`
}

export function getPopulationTilesForBounds(
  bounds: PopulationBounds,
  coverageBounds: PopulationBounds
): PopulationTile[] {
  const clampedBounds = clampPopulationBounds(bounds, coverageBounds)
  if (!clampedBounds) {
    return []
  }

  const minTileX = Math.floor(
    (clampedBounds.minLon - coverageBounds.minLon) / POPULATION_TILE_LON_DEGREES
  )
  const maxTileX = Math.floor(
    Math.max(
      0,
      (clampedBounds.maxLon - coverageBounds.minLon - Number.EPSILON) /
        POPULATION_TILE_LON_DEGREES
    )
  )
  const minTileY = Math.floor(
    (clampedBounds.minLat - coverageBounds.minLat) / POPULATION_TILE_LAT_DEGREES
  )
  const maxTileY = Math.floor(
    Math.max(
      0,
      (clampedBounds.maxLat - coverageBounds.minLat - Number.EPSILON) /
        POPULATION_TILE_LAT_DEGREES
    )
  )

  const tiles: PopulationTile[] = []

  for (let tileY = minTileY; tileY <= maxTileY; tileY += 1) {
    for (let tileX = minTileX; tileX <= maxTileX; tileX += 1) {
      const tileMinLon = coverageBounds.minLon + tileX * POPULATION_TILE_LON_DEGREES
      const tileMinLat = coverageBounds.minLat + tileY * POPULATION_TILE_LAT_DEGREES
      const tileMaxLon = Math.min(
        tileMinLon + POPULATION_TILE_LON_DEGREES,
        coverageBounds.maxLon
      )
      const tileMaxLat = Math.min(
        tileMinLat + POPULATION_TILE_LAT_DEGREES,
        coverageBounds.maxLat
      )

      tiles.push({
        key: buildPopulationTileKey(tileX, tileY),
        bounds: {
          minLat: tileMinLat,
          minLon: tileMinLon,
          maxLat: tileMaxLat,
          maxLon: tileMaxLon,
        },
      })
    }
  }

  return tiles
}

export function getPopulationTileCoverageKey(
  bounds: PopulationBounds,
  coverageBounds: PopulationBounds
): string {
  const tiles = getPopulationTilesForBounds(bounds, coverageBounds)
  if (tiles.length === 0) {
    return 'empty'
  }
  return tiles.map((tile) => tile.key).join('|')
}

export function mergePopulationGridTiles(
  tileCollections: PopulationGridCellFeatureCollection[]
): PopulationGridCellFeatureCollection {
  if (tileCollections.length === 0) {
    return EMPTY_POPULATION_GRID
  }

  return {
    type: 'FeatureCollection',
    features: tileCollections.flatMap((collection) => collection.features),
  }
}
