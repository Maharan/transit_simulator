type CoordinateField = 'lat' | 'lon'
type Endpoint = 'from' | 'to'

type CoordinateInput = {
  lat: string
  lon: string
}

type SelectedCoordinatePoint = {
  lat: number
  lon: number
}

export type {
  CoordinateField,
  Endpoint,
  CoordinateInput,
  SelectedCoordinatePoint,
}
