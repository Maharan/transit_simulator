import type { Feature, Point } from 'geojson'

import {
  EMPTY_POPULATION_DOTS,
  type PopulationDotFeatureCollection,
  type PopulationGridCellFeatureCollection,
} from './types'

const PEOPLE_PER_DOT = 100

type Coordinate = [number, number]
type CellCorners = {
  lowerLeft: Coordinate
  lowerRight: Coordinate
  upperRight: Coordinate
  upperLeft: Coordinate
}

function interpolateSquarePoint(
  lowerLeft: Coordinate,
  lowerRight: Coordinate,
  upperRight: Coordinate,
  upperLeft: Coordinate,
  u: number,
  v: number
): Coordinate {
  const longitude =
    (1 - u) * (1 - v) * lowerLeft[0] +
    u * (1 - v) * lowerRight[0] +
    u * v * upperRight[0] +
    (1 - u) * v * upperLeft[0]
  const latitude =
    (1 - u) * (1 - v) * lowerLeft[1] +
    u * (1 - v) * lowerRight[1] +
    u * v * upperRight[1] +
    (1 - u) * v * upperLeft[1]
  return [longitude, latitude]
}

function buildCellDots(
  corners: CellCorners,
  populationEstimate: number
): Feature<Point, Record<string, never>>[] {
  const dotCount = Math.floor(populationEstimate / PEOPLE_PER_DOT)
  if (dotCount <= 0) {
    return []
  }

  const columns = Math.ceil(Math.sqrt(dotCount))
  const rows = Math.ceil(dotCount / columns)
  let dotsPlaced = 0

  const dots: Feature<Point, Record<string, never>>[] = []
  for (let rowIndex = 0; rowIndex < rows; rowIndex += 1) {
    const rowDotCount = Math.min(columns, dotCount - dotsPlaced)
    const centeredColumnOffset = (columns - rowDotCount) / 2
    const v = (rowIndex + 0.5) / rows

    for (let columnIndex = 0; columnIndex < rowDotCount; columnIndex += 1) {
      const u = (centeredColumnOffset + columnIndex + 0.5) / columns
      const [longitude, latitude] = interpolateSquarePoint(
        corners.lowerLeft,
        corners.lowerRight,
        corners.upperRight,
        corners.upperLeft,
        u,
        v
      )
      dots.push({
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'Point',
          coordinates: [longitude, latitude],
        },
      })
      dotsPlaced += 1
    }
  }

  return dots
}

export function buildPopulationDotFeatureCollection(
  populationGrid: PopulationGridCellFeatureCollection | null
): PopulationDotFeatureCollection {
  if (!populationGrid) {
    return EMPTY_POPULATION_DOTS
  }

  return {
    type: 'FeatureCollection',
    features: populationGrid.features.flatMap((feature) => {
      const populationEstimate = Number(feature.properties?.population_estimate ?? 0)
      const ring = feature.geometry.coordinates[0]
      if (populationEstimate <= 0 || ring.length < 4) {
        return []
      }

      return buildCellDots(
        {
          lowerLeft: ring[0] as Coordinate,
          lowerRight: ring[1] as Coordinate,
          upperRight: ring[2] as Coordinate,
          upperLeft: ring[3] as Coordinate,
        },
        populationEstimate
      )
    }),
  }
}
