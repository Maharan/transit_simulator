import test from 'node:test'
import assert from 'node:assert/strict'

import {
  clampPopulationBounds,
  getPopulationTileCoverageKey,
  getPopulationTilesForBounds,
  mergePopulationGridTiles,
} from '../src/features/demographics/populationTiles.ts'
import { EMPTY_POPULATION_GRID, type PopulationBounds } from '../src/features/demographics/types.ts'

const HAMBURG_BOUNDS: PopulationBounds = {
  minLon: 8,
  minLat: 52.8,
  maxLon: 10.8,
  maxLat: 54.2,
}

test('getPopulationTilesForBounds returns the intersecting 0.2 degree tiles', () => {
  const tiles = getPopulationTilesForBounds(
    {
      minLon: 8.05,
      minLat: 52.85,
      maxLon: 8.35,
      maxLat: 53.15,
    },
    HAMBURG_BOUNDS
  )

  assert.deepEqual(
    tiles.map((tile) => tile.key),
    ['0:0', '1:0', '0:1', '1:1']
  )
  assert.deepEqual(tiles[0]?.bounds, {
    minLon: 8,
    minLat: 52.8,
    maxLon: 8.2,
    maxLat: 53,
  })
})

test('getPopulationTileCoverageKey stays stable within the same tile coverage', () => {
  const firstKey = getPopulationTileCoverageKey(
    {
      minLon: 9.91,
      minLat: 53.52,
      maxLon: 10.04,
      maxLat: 53.64,
    },
    HAMBURG_BOUNDS
  )
  const secondKey = getPopulationTileCoverageKey(
    {
      minLon: 9.93,
      minLat: 53.53,
      maxLon: 10.05,
      maxLat: 53.65,
    },
    HAMBURG_BOUNDS
  )
  const shiftedKey = getPopulationTileCoverageKey(
    {
      minLon: 10.01,
      minLat: 53.53,
      maxLon: 10.21,
      maxLat: 53.65,
    },
    HAMBURG_BOUNDS
  )

  assert.equal(firstKey, secondKey)
  assert.notEqual(firstKey, shiftedKey)
})

test('clampPopulationBounds clips bounds outside the supported coverage', () => {
  assert.deepEqual(
    clampPopulationBounds(
      {
        minLon: 7.5,
        minLat: 52.6,
        maxLon: 8.15,
        maxLat: 52.95,
      },
      HAMBURG_BOUNDS
    ),
    {
      minLon: 8,
      minLat: 52.8,
      maxLon: 8.15,
      maxLat: 52.95,
    }
  )
})

test('mergePopulationGridTiles concatenates tile features and handles empty input', () => {
  const merged = mergePopulationGridTiles([
    {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { population_estimate: 200 },
          geometry: {
            type: 'Polygon',
            coordinates: [[[8, 53], [8.1, 53], [8.1, 53.1], [8, 53.1], [8, 53]]],
          },
        },
      ],
    },
    {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { population_estimate: 400 },
          geometry: {
            type: 'Polygon',
            coordinates: [[[8.1, 53], [8.2, 53], [8.2, 53.1], [8.1, 53.1], [8.1, 53]]],
          },
        },
      ],
    },
  ])

  assert.equal(merged.features.length, 2)
  assert.deepEqual(mergePopulationGridTiles([]), EMPTY_POPULATION_GRID)
})
