type NetworkLineFamily = 'u_bahn' | 's_bahn' | 'regional' | 'a_line'

type NetworkLineFeatureProperties = {
  line_id: string
  line_family: NetworkLineFamily
  color: string
  offset_px: number
}

type NetworkLineFeature = {
  type: 'Feature'
  properties: NetworkLineFeatureProperties
  geometry: {
    type: 'LineString' | 'MultiLineString'
    coordinates: Array<[number, number]> | Array<Array<[number, number]>>
  }
}

type NetworkLineFeatureCollection = {
  type: 'FeatureCollection'
  features: NetworkLineFeature[]
}

export type {
  NetworkLineFamily,
  NetworkLineFeature,
  NetworkLineFeatureCollection,
  NetworkLineFeatureProperties,
}
