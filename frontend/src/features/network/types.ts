import type { FeatureCollection, LineString, MultiLineString } from 'geojson'

export type LineFamily = 'u_bahn' | 's_bahn' | 'a_line' | 'regional'

export type NetworkLineProperties = {
  line_id: string
  line_family: LineFamily
  color: string
  offset_px: number
}

export type NetworkLineFeatureCollection = FeatureCollection<
  LineString | MultiLineString,
  NetworkLineProperties
>

export const EMPTY_NETWORK_LINE_FEATURES: NetworkLineFeatureCollection = {
  type: 'FeatureCollection',
  features: [],
}

export type LineFamilyVisibility = Record<LineFamily, boolean>
