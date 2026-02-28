import type { FeatureCollection, Point, Polygon } from 'geojson'

export type PopulationGridCellProperties = {
  population_estimate: number
}

export type PopulationGridCellFeatureCollection = FeatureCollection<
  Polygon,
  PopulationGridCellProperties
>

export type PopulationDotFeatureCollection = FeatureCollection<Point, Record<string, never>>

export type PopulationBounds = {
  minLat: number
  minLon: number
  maxLat: number
  maxLon: number
}

export const EMPTY_POPULATION_GRID: PopulationGridCellFeatureCollection = {
  type: 'FeatureCollection',
  features: [],
}

export const EMPTY_POPULATION_DOTS: PopulationDotFeatureCollection = {
  type: 'FeatureCollection',
  features: [],
}
