import { useEffect, useMemo, useRef, type MutableRefObject } from 'react'
import maplibregl from 'maplibre-gl'

import './mapDisplay.css'
import { fetchFloorSpaceDensity } from '../services/floorSpaceApi'
import { fetchRapidTransitNetworkLines } from '../services/networkLinesApi'
import {
  ENDPOINT_SOURCE_ID,
  POPULATION_HEATMAP_LAYER_ID,
  POPULATION_HEATMAP_SOURCE_ID,
  POPULATION_SURFACE_COLOR_STOPS,
  RAPID_TRANSIT_NETWORK_SOURCE_ID,
  ROUTE_SOURCE_ID,
  STOP_SOURCE_ID,
  addPopulationHeatmapSourceAndLayer,
  addRapidTransitNetworkSourceAndLayers,
  addRouteSourcesAndLayers,
  bindRouteInteractionHandlers,
  setPopulationHeatmapVisibility,
  setRapidTransitNetworkVisibility,
} from '../services/mapLayerConfig'
import { OSM_RASTER_STYLE } from '../services/mapStyle'
import { buildRouteMapData } from '../services/routeMapData'
import type {
  FloorSpaceDensityFeature,
  FloorSpaceDensityFeatureCollection,
  PopulationSurfaceFeature,
  PopulationSurfaceFeatureCollection,
} from '../types/floorSpace.types'
import type { NetworkLineFeatureCollection } from '../types/networkLines.types'
import type { RouteResponse } from '../types/route.types'

const FLOOR_SPACE_DATASET_RELEASE = '2023-04-01'
const FLOOR_SPACE_GRID_RESOLUTION_M = 100
const METERS_PER_LATITUDE_DEGREE = 111_320
const INTEGER_FORMATTER = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0,
})
const POPULATION_SURFACE_LEGEND_STOPS = POPULATION_SURFACE_COLOR_STOPS.filter(
  ({ value }) => value >= 0,
)
const POPULATION_SURFACE_LEGEND_MAX =
  POPULATION_SURFACE_LEGEND_STOPS[
    POPULATION_SURFACE_LEGEND_STOPS.length - 1
  ]?.value ?? 1
const POPULATION_SURFACE_LEGEND_GRADIENT = `linear-gradient(90deg, ${POPULATION_SURFACE_LEGEND_STOPS.map(
  ({ value, color }) =>
    `${color} ${(value / POPULATION_SURFACE_LEGEND_MAX) * 100}%`,
).join(', ')})`
const POPULATION_SURFACE_LEGEND_ITEMS = POPULATION_SURFACE_LEGEND_STOPS.map(
  ({ value }, index) => ({
    value,
    positionPercent: (value / POPULATION_SURFACE_LEGEND_MAX) * 100,
    anchor:
      index === 0
        ? 'start'
        : index === POPULATION_SURFACE_LEGEND_STOPS.length - 1
          ? 'end'
          : 'center',
    label:
      index === POPULATION_SURFACE_LEGEND_STOPS.length - 1
        ? `${formatLegendDensityValue(value)}+`
        : formatLegendDensityValue(value),
  }),
)
const EMPTY_FEATURE_COLLECTION: FloorSpaceDensityFeatureCollection = {
  type: 'FeatureCollection',
  features: [],
}
const EMPTY_SURFACE_FEATURE_COLLECTION: PopulationSurfaceFeatureCollection = {
  type: 'FeatureCollection',
  features: [],
}
const EMPTY_NETWORK_LINE_FEATURE_COLLECTION: NetworkLineFeatureCollection = {
  type: 'FeatureCollection',
  features: [],
}

type MapDisplayProps = {
  routeResult: RouteResponse | null
  showPopulationHeatmap: boolean
  showRapidTransitLines: boolean
}

function MapDisplay({
  routeResult,
  showPopulationHeatmap,
  showRapidTransitLines,
}: MapDisplayProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const routeMapDataRef = useRef(buildRouteMapData(routeResult))
  const showPopulationHeatmapRef = useRef(showPopulationHeatmap)
  const showRapidTransitLinesRef = useRef(showRapidTransitLines)
  const heatmapRequestRef = useRef<AbortController | null>(null)
  const rapidTransitRequestRef = useRef<AbortController | null>(null)
  const hasLoadedRapidTransitNetworkRef = useRef(false)
  const populationSurfacePopupRef = useRef<maplibregl.Popup | null>(null)

  const routeMapData = useMemo(
    () => buildRouteMapData(routeResult),
    [routeResult],
  )

  useEffect(() => {
    routeMapDataRef.current = routeMapData
  }, [routeMapData])

  useEffect(() => {
    showPopulationHeatmapRef.current = showPopulationHeatmap
  }, [showPopulationHeatmap])

  useEffect(() => {
    showRapidTransitLinesRef.current = showRapidTransitLines
  }, [showRapidTransitLines])

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) {
      return
    }

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: OSM_RASTER_STYLE,
      center: [9.99, 53.55],
      zoom: 11,
    })

    map.addControl(new maplibregl.NavigationControl(), 'top-right')
    mapRef.current = map
    const populationSurfacePopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 12,
      maxWidth: '260px',
    })
    populationSurfacePopupRef.current = populationSurfacePopup

    const handlePopulationSurfaceMove = (
      event: maplibregl.MapLayerMouseEvent,
    ) => {
      if (!showPopulationHeatmapRef.current) {
        return
      }

      const feature = event.features?.[0]
      if (!feature) {
        return
      }

      const densityPerSqKm = parseNumericProperty(
        feature.properties?.population_density_sqkm,
      )
      const cellPopulationEstimate = parseNumericProperty(
        feature.properties?.population_estimate,
      )

      map.getCanvas().style.cursor = 'pointer'
      populationSurfacePopup
        .setLngLat(event.lngLat)
        .setHTML(
          buildPopulationSurfacePopupHtml({
            densityPerSqKm,
            cellPopulationEstimate,
          }),
        )
        .addTo(map)
    }

    const handlePopulationSurfaceLeave = () => {
      map.getCanvas().style.cursor = ''
      populationSurfacePopup.remove()
    }

    map.on('load', () => {
      addPopulationHeatmapSourceAndLayer(map)
      addRapidTransitNetworkSourceAndLayers(map)
      addRouteSourcesAndLayers(map)
      bindRouteInteractionHandlers(map)
      setPopulationHeatmapVisibility(map, showPopulationHeatmapRef.current)
      setRapidTransitNetworkVisibility(map, showRapidTransitLinesRef.current)
      updateMapRouteData(map, routeMapDataRef.current)
      void refreshPopulationHeatmapData(map, {
        shouldShow: showPopulationHeatmapRef.current,
        requestRef: heatmapRequestRef,
      })
      void ensureRapidTransitNetworkData(map, {
        shouldShow: showRapidTransitLinesRef.current,
        requestRef: rapidTransitRequestRef,
        hasLoadedRef: hasLoadedRapidTransitNetworkRef,
      })
    })

    const handleMoveEnd = () => {
      void refreshPopulationHeatmapData(map, {
        shouldShow: showPopulationHeatmapRef.current,
        requestRef: heatmapRequestRef,
      })
    }

    map.on('moveend', handleMoveEnd)
    map.on('mousemove', POPULATION_HEATMAP_LAYER_ID, handlePopulationSurfaceMove)
    map.on('mouseleave', POPULATION_HEATMAP_LAYER_ID, handlePopulationSurfaceLeave)

    return () => {
      cancelPopulationHeatmapRequest(heatmapRequestRef)
      cancelRapidTransitNetworkRequest(rapidTransitRequestRef)
      populationSurfacePopup.remove()
      map.off('moveend', handleMoveEnd)
      map.off('mousemove', POPULATION_HEATMAP_LAYER_ID, handlePopulationSurfaceMove)
      map.off('mouseleave', POPULATION_HEATMAP_LAYER_ID, handlePopulationSurfaceLeave)
      map.remove()
      mapRef.current = null
      populationSurfacePopupRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) {
      return
    }
    updateMapRouteData(map, routeMapData)
  }, [routeMapData])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) {
      return
    }

    setPopulationHeatmapVisibility(map, showPopulationHeatmap)
    if (showPopulationHeatmap) {
      void refreshPopulationHeatmapData(map, {
        shouldShow: true,
        requestRef: heatmapRequestRef,
      })
      return
    }

    cancelPopulationHeatmapRequest(heatmapRequestRef)
    populationSurfacePopupRef.current?.remove()
    map.getCanvas().style.cursor = ''
    setPopulationHeatmapData(map, EMPTY_FEATURE_COLLECTION)
  }, [showPopulationHeatmap])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) {
      return
    }

    setRapidTransitNetworkVisibility(map, showRapidTransitLines)
    void ensureRapidTransitNetworkData(map, {
      shouldShow: showRapidTransitLines,
      requestRef: rapidTransitRequestRef,
      hasLoadedRef: hasLoadedRapidTransitNetworkRef,
    })
  }, [showRapidTransitLines])

  return (
    <div className="map-display">
      <div ref={mapContainerRef} className="map-canvas" />
      <div className="map-legend map-legend--routes">
        <span className="legend-line transit" />
        <span>Planned ride</span>
        <span className="legend-line transfer" />
        <span>Transfer / walk</span>
        {showRapidTransitLines && (
          <>
            <span className="legend-swatch rapid-transit" />
            <span className="legend-copy">
              <span>U-Bahn / S-Bahn</span>
              <small>Static network overlay</small>
            </span>
          </>
        )}
      </div>
      {showPopulationHeatmap && (
        <div className="map-surface-legend">
          <div className="surface-legend-title">Population Surface</div>
          <div className="surface-legend-subtitle">
            Smoothed scale, people per km^2
          </div>
          <div
            className="surface-legend-gradient"
            style={{ backgroundImage: POPULATION_SURFACE_LEGEND_GRADIENT }}
          />
          <div className="surface-legend-ticks">
            {POPULATION_SURFACE_LEGEND_ITEMS.map((item, index) => (
              <div
                key={item.value}
                className={`surface-legend-tick surface-legend-tick--${item.anchor} ${
                  index % 2 === 0
                    ? 'surface-legend-tick--top'
                    : 'surface-legend-tick--bottom'
                }`}
                style={{ left: `${item.positionPercent}%` }}
              >
                <span className="surface-legend-tick-mark" />
                <span className="surface-legend-tick-label">{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function updateMapRouteData(
  map: maplibregl.Map,
  routeMapData: ReturnType<typeof buildRouteMapData>,
): void {
  const routeSource = map.getSource(ROUTE_SOURCE_ID) as maplibregl.GeoJSONSource | undefined
  const stopSource = map.getSource(STOP_SOURCE_ID) as maplibregl.GeoJSONSource | undefined
  const endpointSource = map.getSource(ENDPOINT_SOURCE_ID) as maplibregl.GeoJSONSource | undefined

  if (!routeSource || !stopSource || !endpointSource) {
    return
  }

  routeSource.setData(routeMapData.lineCollection as never)
  stopSource.setData(routeMapData.stopCollection as never)
  endpointSource.setData(routeMapData.endpointCollection as never)

  if (routeMapData.bounds) {
    map.fitBounds(routeMapData.bounds, {
      padding: 52,
      duration: 850,
      maxZoom: 15,
    })
  }
}

function setPopulationHeatmapData(
  map: maplibregl.Map,
  featureCollection: FloorSpaceDensityFeatureCollection,
): void {
  const heatmapSource = map.getSource(
    POPULATION_HEATMAP_SOURCE_ID,
  ) as maplibregl.GeoJSONSource | undefined
  if (!heatmapSource) {
    return
  }
  heatmapSource.setData(
    buildPopulationSurfaceFeatureCollection(
      featureCollection,
      FLOOR_SPACE_GRID_RESOLUTION_M,
    ) as never,
  )
}

function setRapidTransitNetworkData(
  map: maplibregl.Map,
  featureCollection: NetworkLineFeatureCollection,
): void {
  const rapidTransitSource = map.getSource(
    RAPID_TRANSIT_NETWORK_SOURCE_ID,
  ) as maplibregl.GeoJSONSource | undefined
  if (!rapidTransitSource) {
    return
  }
  rapidTransitSource.setData(featureCollection as never)
}

function cancelPopulationHeatmapRequest(
  requestRef: MutableRefObject<AbortController | null>,
): void {
  requestRef.current?.abort()
  requestRef.current = null
}

function cancelRapidTransitNetworkRequest(
  requestRef: MutableRefObject<AbortController | null>,
): void {
  requestRef.current?.abort()
  requestRef.current = null
}

function parseNumericProperty(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }

  return null
}

function formatLegendDensityValue(value: number): string {
  if (value <= 0) {
    return '0'
  }

  if (value % 1000 === 0) {
    return `${value / 1000}k`
  }

  return `${(value / 1000).toFixed(1)}k`
}

function buildPopulationSurfacePopupHtml({
  densityPerSqKm,
  cellPopulationEstimate,
}: {
  densityPerSqKm: number | null
  cellPopulationEstimate: number | null
}): string {
  const densityLabel =
    densityPerSqKm === null
      ? 'Unavailable'
      : `${INTEGER_FORMATTER.format(densityPerSqKm)} people/km^2`
  const estimateLabel =
    cellPopulationEstimate === null
      ? 'Unavailable'
      : `${INTEGER_FORMATTER.format(cellPopulationEstimate)} people`

  return `
    <div class="population-surface-popup">
      <div class="population-surface-popup__title">Population density</div>
      <div class="population-surface-popup__value">${densityLabel}</div>
      <div class="population-surface-popup__meta">Estimated in this cell: ${estimateLabel}</div>
    </div>
  `
}

function buildPopulationSurfaceFeatureCollection(
  featureCollection: FloorSpaceDensityFeatureCollection,
  gridResolutionMeters: number,
): PopulationSurfaceFeatureCollection {
  if (featureCollection.features.length === 0) {
    return EMPTY_SURFACE_FEATURE_COLLECTION
  }

  return {
    type: 'FeatureCollection',
    features: featureCollection.features.map((feature) =>
      buildPopulationSurfaceFeature(feature, gridResolutionMeters),
    ),
  }
}

function buildPopulationSurfaceFeature(
  feature: FloorSpaceDensityFeature,
  gridResolutionMeters: number,
): PopulationSurfaceFeature {
  const [longitude, latitude] = feature.geometry.coordinates
  const halfSideMeters = gridResolutionMeters / 2
  const latitudeDelta = halfSideMeters / METERS_PER_LATITUDE_DEGREE
  const longitudeDelta =
    halfSideMeters /
    Math.max(
      METERS_PER_LATITUDE_DEGREE * Math.cos((latitude * Math.PI) / 180),
      1e-6,
    )
  const exteriorRing: Array<[number, number]> = [
    [longitude - longitudeDelta, latitude - latitudeDelta],
    [longitude + longitudeDelta, latitude - latitudeDelta],
    [longitude + longitudeDelta, latitude + latitudeDelta],
    [longitude - longitudeDelta, latitude + latitudeDelta],
    [longitude - longitudeDelta, latitude - latitudeDelta],
  ]

  return {
    type: 'Feature' as const,
    properties: feature.properties,
    geometry: {
      type: 'Polygon' as const,
      coordinates: [exteriorRing],
    },
  }
}

async function ensureRapidTransitNetworkData(
  map: maplibregl.Map,
  {
    shouldShow,
    requestRef,
    hasLoadedRef,
  }: {
    shouldShow: boolean
    requestRef: MutableRefObject<AbortController | null>
    hasLoadedRef: MutableRefObject<boolean>
  },
): Promise<void> {
  if (!shouldShow || hasLoadedRef.current) {
    return
  }

  requestRef.current?.abort()
  const controller = new AbortController()
  requestRef.current = controller

  try {
    const featureCollection = await fetchRapidTransitNetworkLines(controller.signal)

    if (requestRef.current !== controller) {
      return
    }

    setRapidTransitNetworkData(map, featureCollection)
    hasLoadedRef.current = true
  } catch (error) {
    if (controller.signal.aborted) {
      return
    }
    setRapidTransitNetworkData(map, EMPTY_NETWORK_LINE_FEATURE_COLLECTION)
    console.error('Failed to load rapid transit network lines.', error)
  } finally {
    if (requestRef.current === controller) {
      requestRef.current = null
    }
  }
}

async function refreshPopulationHeatmapData(
  map: maplibregl.Map,
  {
    shouldShow,
    requestRef,
  }: {
    shouldShow: boolean
    requestRef: MutableRefObject<AbortController | null>
  },
): Promise<void> {
  if (!shouldShow) {
    setPopulationHeatmapData(map, EMPTY_FEATURE_COLLECTION)
    return
  }

  const bounds = map.getBounds()
  if (!bounds) {
    return
  }

  requestRef.current?.abort()
  const controller = new AbortController()
  requestRef.current = controller

  try {
    const featureCollection = await fetchFloorSpaceDensity(
      {
        dataset_release: FLOOR_SPACE_DATASET_RELEASE,
        grid_resolution_m: FLOOR_SPACE_GRID_RESOLUTION_M,
        min_lat: bounds.getSouth(),
        min_lon: bounds.getWest(),
        max_lat: bounds.getNorth(),
        max_lon: bounds.getEast(),
      },
      controller.signal,
    )

    if (requestRef.current !== controller) {
      return
    }

    setPopulationHeatmapData(map, featureCollection)
  } catch (error) {
    if (controller.signal.aborted) {
      return
    }
    setPopulationHeatmapData(map, EMPTY_FEATURE_COLLECTION)
    console.error('Failed to load floor-space density heatmap.', error)
  }
}

export { MapDisplay }
