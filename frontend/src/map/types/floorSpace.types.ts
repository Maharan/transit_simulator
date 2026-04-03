type FloorSpaceDensityFeatureProperties = {
  building_count: number
  floor_space_m2: number
  floor_space_density_sqkm: number
  population_estimate: number
  population_density_sqkm: number
}

type FloorSpaceDensityFeature = {
  type: 'Feature'
  properties: FloorSpaceDensityFeatureProperties
  geometry: {
    type: 'Point'
    coordinates: [number, number]
  }
}

type FloorSpaceDensityFeatureCollection = {
  type: 'FeatureCollection'
  features: FloorSpaceDensityFeature[]
}

type PopulationSurfaceFeature = {
  type: 'Feature'
  properties: FloorSpaceDensityFeatureProperties
  geometry: {
    type: 'Polygon'
    coordinates: Array<Array<[number, number]>>
  }
}

type PopulationSurfaceFeatureCollection = {
  type: 'FeatureCollection'
  features: PopulationSurfaceFeature[]
}

type FloorSpaceDensityRequest = {
  dataset_release: string
  grid_resolution_m: number
  min_lat: number
  min_lon: number
  max_lat: number
  max_lon: number
}

export type {
  FloorSpaceDensityFeature,
  FloorSpaceDensityFeatureCollection,
  FloorSpaceDensityFeatureProperties,
  FloorSpaceDensityRequest,
  PopulationSurfaceFeature,
  PopulationSurfaceFeatureCollection,
}
