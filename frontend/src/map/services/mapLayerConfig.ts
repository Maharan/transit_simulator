import maplibregl from 'maplibre-gl'

const ROUTE_SOURCE_ID = 'route-segments-source'
const STOP_SOURCE_ID = 'route-stops-source'
const ENDPOINT_SOURCE_ID = 'route-endpoints-source'

const ROUTE_TRANSIT_LAYER_ID = 'route-transit-layer'
const ROUTE_TRANSFER_LAYER_ID = 'route-transfer-layer'
const STOP_LAYER_ID = 'route-stops-layer'
const ENDPOINT_LAYER_ID = 'route-endpoints-layer'

function addRouteSourcesAndLayers(map: maplibregl.Map): void {
  map.addSource(ROUTE_SOURCE_ID, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })
  map.addSource(STOP_SOURCE_ID, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })
  map.addSource(ENDPOINT_SOURCE_ID, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })

  map.addLayer({
    id: ROUTE_TRANSIT_LAYER_ID,
    type: 'line',
    source: ROUTE_SOURCE_ID,
    filter: ['match', ['get', 'edgeKind'], ['trip', 'ride'], true, false],
    paint: {
      'line-color': '#1d4ed8',
      'line-width': 4,
      'line-opacity': 0.85,
    },
  })

  map.addLayer({
    id: ROUTE_TRANSFER_LAYER_ID,
    type: 'line',
    source: ROUTE_SOURCE_ID,
    filter: ['!', ['match', ['get', 'edgeKind'], ['trip', 'ride'], true, false]],
    paint: {
      'line-color': '#d97706',
      'line-width': 3,
      'line-opacity': 0.9,
      'line-dasharray': [1.5, 1.5],
    },
  })

  map.addLayer({
    id: STOP_LAYER_ID,
    type: 'circle',
    source: STOP_SOURCE_ID,
    paint: {
      'circle-radius': 4.5,
      'circle-color': '#ffffff',
      'circle-stroke-color': '#1f2937',
      'circle-stroke-width': 1.5,
      'circle-opacity': 0.95,
    },
  })

  map.addLayer({
    id: ENDPOINT_LAYER_ID,
    type: 'circle',
    source: ENDPOINT_SOURCE_ID,
    paint: {
      'circle-radius': 7,
      'circle-color': [
        'match',
        ['get', 'endpointRole'],
        'start',
        '#16a34a',
        'end',
        '#dc2626',
        '#6b7280',
      ],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 2,
    },
  })
}

function bindRouteInteractionHandlers(map: maplibregl.Map): void {
  map.on('mouseenter', STOP_LAYER_ID, () => {
    map.getCanvas().style.cursor = 'pointer'
  })
  map.on('mouseleave', STOP_LAYER_ID, () => {
    map.getCanvas().style.cursor = ''
  })
  map.on('mouseenter', ENDPOINT_LAYER_ID, () => {
    map.getCanvas().style.cursor = 'pointer'
  })
  map.on('mouseleave', ENDPOINT_LAYER_ID, () => {
    map.getCanvas().style.cursor = ''
  })

  map.on('click', STOP_LAYER_ID, (event) => {
    const feature = event.features?.[0]
    if (!feature || feature.geometry.type !== 'Point') {
      return
    }
    const coordinates = feature.geometry.coordinates as [number, number]
    const stopName = String(feature.properties?.stopName ?? 'Stop')
    new maplibregl.Popup({ closeButton: false, offset: 8 })
      .setLngLat(coordinates)
      .setText(stopName)
      .addTo(map)
  })

  map.on('click', ENDPOINT_LAYER_ID, (event) => {
    const feature = event.features?.[0]
    if (!feature || feature.geometry.type !== 'Point') {
      return
    }
    const coordinates = feature.geometry.coordinates as [number, number]
    const stopName = String(feature.properties?.stopName ?? 'Endpoint')
    const role = String(feature.properties?.endpointRole ?? '')
    const label =
      role === 'start'
        ? `Start: ${stopName}`
        : role === 'end'
          ? `End: ${stopName}`
          : stopName
    new maplibregl.Popup({ closeButton: false, offset: 8 })
      .setLngLat(coordinates)
      .setText(label)
      .addTo(map)
  })
}

export {
  ROUTE_SOURCE_ID,
  STOP_SOURCE_ID,
  ENDPOINT_SOURCE_ID,
  addRouteSourcesAndLayers,
  bindRouteInteractionHandlers,
}
