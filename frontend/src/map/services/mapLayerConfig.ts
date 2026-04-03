import maplibregl from 'maplibre-gl'

const ROUTE_SOURCE_ID = 'route-segments-source'
const STOP_SOURCE_ID = 'route-stops-source'
const ENDPOINT_SOURCE_ID = 'route-endpoints-source'
const POPULATION_HEATMAP_SOURCE_ID = 'population-heatmap-source'
const RAPID_TRANSIT_NETWORK_SOURCE_ID = 'rapid-transit-network-source'

const ROUTE_TRANSIT_LAYER_ID = 'route-transit-layer'
const ROUTE_TRANSFER_LAYER_ID = 'route-transfer-layer'
const STOP_LAYER_ID = 'route-stops-layer'
const ENDPOINT_LAYER_ID = 'route-endpoints-layer'
const POPULATION_HEATMAP_LAYER_ID = 'population-heatmap-layer'
const RAPID_TRANSIT_NETWORK_CASING_LAYER_ID =
  'rapid-transit-network-casing-layer'
const RAPID_TRANSIT_NETWORK_LAYER_ID = 'rapid-transit-network-layer'
const POPULATION_SURFACE_COLOR_STOPS = [
  { value: -1, color: '#ffffff' },
  { value: 0, color: '#fffef7' },
  { value: 2500, color: '#fef3c7' },
  { value: 7000, color: '#fde047' },
  { value: 12000, color: '#fb923c' },
  { value: 18000, color: '#ef4444' },
  { value: 22000, color: '#8b5cf6' },
  { value: 30000, color: '#5b21b6' },
] as const

function buildPopulationSurfaceFillColorExpression(): maplibregl.ExpressionSpecification {
  return [
    'interpolate',
    ['linear'],
    ['coalesce', ['get', 'population_density_sqkm'], -1],
    ...POPULATION_SURFACE_COLOR_STOPS.flatMap(({ value, color }) => [value, color]),
  ] as maplibregl.ExpressionSpecification
}

function addPopulationHeatmapSourceAndLayer(map: maplibregl.Map): void {
  map.addSource(POPULATION_HEATMAP_SOURCE_ID, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })

  map.addLayer({
    id: POPULATION_HEATMAP_LAYER_ID,
    type: 'fill',
    source: POPULATION_HEATMAP_SOURCE_ID,
    paint: {
      'fill-color': buildPopulationSurfaceFillColorExpression(),
      'fill-opacity': 0.72,
      'fill-outline-color': 'rgba(59, 130, 246, 0.16)',
    },
    layout: {
      visibility: 'none',
    },
  })
}

function addRapidTransitNetworkSourceAndLayers(map: maplibregl.Map): void {
  map.addSource(RAPID_TRANSIT_NETWORK_SOURCE_ID, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })

  map.addLayer({
    id: RAPID_TRANSIT_NETWORK_CASING_LAYER_ID,
    type: 'line',
    source: RAPID_TRANSIT_NETWORK_SOURCE_ID,
    paint: {
      'line-color': 'rgba(255, 255, 255, 0.9)',
      'line-width': [
        'interpolate',
        ['linear'],
        ['zoom'],
        9,
        3,
        12,
        4.6,
        15,
        6.2,
      ],
      'line-offset': ['coalesce', ['to-number', ['get', 'offset_px']], 0],
      'line-opacity': 0.85,
    },
    layout: {
      'line-cap': 'round',
      'line-join': 'round',
      visibility: 'none',
    },
  })

  map.addLayer({
    id: RAPID_TRANSIT_NETWORK_LAYER_ID,
    type: 'line',
    source: RAPID_TRANSIT_NETWORK_SOURCE_ID,
    paint: {
      'line-color': ['coalesce', ['get', 'color'], '#475569'],
      'line-width': [
        'interpolate',
        ['linear'],
        ['zoom'],
        9,
        1.8,
        12,
        2.8,
        15,
        4.2,
      ],
      'line-offset': ['coalesce', ['to-number', ['get', 'offset_px']], 0],
      'line-opacity': 0.88,
    },
    layout: {
      'line-cap': 'round',
      'line-join': 'round',
      visibility: 'none',
    },
  })
}

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

function setPopulationHeatmapVisibility(
  map: maplibregl.Map,
  isVisible: boolean,
): void {
  map.setLayoutProperty(
    POPULATION_HEATMAP_LAYER_ID,
    'visibility',
    isVisible ? 'visible' : 'none',
  )
}

function setRapidTransitNetworkVisibility(
  map: maplibregl.Map,
  isVisible: boolean,
): void {
  const visibility = isVisible ? 'visible' : 'none'
  map.setLayoutProperty(
    RAPID_TRANSIT_NETWORK_CASING_LAYER_ID,
    'visibility',
    visibility,
  )
  map.setLayoutProperty(RAPID_TRANSIT_NETWORK_LAYER_ID, 'visibility', visibility)
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
  POPULATION_HEATMAP_SOURCE_ID,
  RAPID_TRANSIT_NETWORK_SOURCE_ID,
  POPULATION_HEATMAP_LAYER_ID,
  RAPID_TRANSIT_NETWORK_LAYER_ID,
  POPULATION_SURFACE_COLOR_STOPS,
  addRouteSourcesAndLayers,
  addPopulationHeatmapSourceAndLayer,
  addRapidTransitNetworkSourceAndLayers,
  bindRouteInteractionHandlers,
  setPopulationHeatmapVisibility,
  setRapidTransitNetworkVisibility,
}
