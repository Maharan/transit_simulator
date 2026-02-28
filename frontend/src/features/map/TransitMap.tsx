import { useEffect, useRef, useState } from 'react'
import maplibregl, { type GeoJSONSource, type LngLatBoundsLike } from 'maplibre-gl'
import type { FeatureCollection, LineString, Point } from 'geojson'
import 'maplibre-gl/dist/maplibre-gl.css'

import {
  EMPTY_POPULATION_DOTS,
  type PopulationBounds,
  type PopulationDotFeatureCollection,
} from '../demographics/types'
import { HAMBURG_CENTER, HAMBURG_MAP_BOUNDS } from './constants'
import type { Coordinate, SegmentProperties, StopProperties } from '../routing/types'
import type { NetworkLineFeatureCollection } from '../network/types'

const ROUTE_SOURCE_ID = 'route-segments-source'
const ROUTE_CASING_LAYER_ID = 'route-segments-casing-layer'
const ROUTE_LAYER_ID = 'route-segments-layer'
const ROUTE_WALK_LAYER_ID = 'route-segments-walk-layer'
const ROUTE_HOVER_LAYER_ID = 'route-segments-hover-layer'
const STOPS_SOURCE_ID = 'route-stops-source'
const STOPS_LAYER_ID = 'route-stops-layer'
const NETWORK_SOURCE_ID = 'network-lines-source'
const NETWORK_LAYER_ID = 'network-lines-layer'
const NETWORK_HALO_LAYER_ID = 'network-lines-halo-layer'
const NETWORK_HOVER_LAYER_ID = 'network-lines-hover-layer'
const POPULATION_SOURCE_ID = 'population-grid-source'
const POPULATION_LAYER_ID = 'population-grid-dot-layer'
const DEFAULT_NETWORK_LINE_OPACITY = 0.5
const ACTIVE_ROUTE_LINE_OPACITY = 1
const POPULATION_DOT_OPACITY = 0.72

type HoverTag = {
  x: number
  y: number
  label: string
}

function parseNumberProperty(value: unknown): number | null {
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

type TransitMapProps = {
  origin: Coordinate | null
  destination: Coordinate | null
  networkLineFeatures: NetworkLineFeatureCollection
  populationDotFeatures: PopulationDotFeatureCollection
  populationHeatmapVisible: boolean
  segmentFeatures: FeatureCollection<LineString, SegmentProperties>
  stopFeatures: FeatureCollection<Point, StopProperties>
  onMapClick: (coord: Coordinate) => void
  onViewportBoundsChange: (bounds: PopulationBounds) => void
}

function TransitMap({
  origin,
  destination,
  networkLineFeatures,
  populationDotFeatures,
  populationHeatmapVisible,
  segmentFeatures,
  stopFeatures,
  onMapClick,
  onViewportBoundsChange,
}: TransitMapProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const mapReadyRef = useRef(false)
  const onMapClickRef = useRef(onMapClick)
  const onViewportBoundsChangeRef = useRef(onViewportBoundsChange)
  const networkLineFeaturesRef = useRef(networkLineFeatures)
  const populationDotFeaturesRef = useRef(populationDotFeatures)
  const populationHeatmapVisibleRef = useRef(populationHeatmapVisible)
  const segmentFeaturesRef = useRef(segmentFeatures)
  const stopFeaturesRef = useRef(stopFeatures)

  const originMarkerRef = useRef<maplibregl.Marker | null>(null)
  const destinationMarkerRef = useRef<maplibregl.Marker | null>(null)
  const [hoveredLineId, setHoveredLineId] = useState<string | null>(null)
  const [hoveredRouteLegIndex, setHoveredRouteLegIndex] = useState<number | null>(null)
  const [hoverTag, setHoverTag] = useState<HoverTag | null>(null)

  useEffect(() => {
    onMapClickRef.current = onMapClick
  }, [onMapClick])

  useEffect(() => {
    onViewportBoundsChangeRef.current = onViewportBoundsChange
  }, [onViewportBoundsChange])

  useEffect(() => {
    networkLineFeaturesRef.current = networkLineFeatures
  }, [networkLineFeatures])

  useEffect(() => {
    populationDotFeaturesRef.current = populationDotFeatures
  }, [populationDotFeatures])

  useEffect(() => {
    populationHeatmapVisibleRef.current = populationHeatmapVisible
  }, [populationHeatmapVisible])

  useEffect(() => {
    segmentFeaturesRef.current = segmentFeatures
  }, [segmentFeatures])

  useEffect(() => {
    stopFeaturesRef.current = stopFeatures
  }, [stopFeatures])

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) {
      return
    }

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      center: HAMBURG_CENTER,
      zoom: 10.7,
      maxBounds: HAMBURG_MAP_BOUNDS as LngLatBoundsLike,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap contributors',
          },
        },
        layers: [
          {
            id: 'osm-base',
            type: 'raster',
            source: 'osm',
          },
        ],
      },
    })

    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')

    const handleClick = (event: maplibregl.MapMouseEvent) => {
      onMapClickRef.current({ lat: event.lngLat.lat, lon: event.lngLat.lng })
    }

    const notifyViewportBounds = () => {
      const bounds = map.getBounds()
      onViewportBoundsChangeRef.current({
        minLat: bounds.getSouth(),
        minLon: bounds.getWest(),
        maxLat: bounds.getNorth(),
        maxLon: bounds.getEast(),
      })
    }

    const handleRouteMouseMove = (
      event: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }
    ) => {
      const feature = event.features?.[0]
      const legIndex = parseNumberProperty(feature?.properties?.leg_index)
      const legLabel =
        feature && typeof feature.properties?.leg_label === 'string'
          ? feature.properties.leg_label
          : null
      if (legIndex === null || !legLabel) {
        setHoveredRouteLegIndex(null)
        setHoverTag(null)
        map.getCanvas().style.cursor = ''
        return
      }
      setHoveredRouteLegIndex(legIndex)
      setHoveredLineId(null)
      setHoverTag({
        x: event.point.x + 12,
        y: event.point.y + 12,
        label: legLabel,
      })
      map.getCanvas().style.cursor = 'pointer'
    }

    const handleRouteMouseLeave = () => {
      setHoveredRouteLegIndex(null)
      setHoverTag(null)
      map.getCanvas().style.cursor = ''
    }

    const handleNetworkMouseMove = (
      event: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }
    ) => {
      const feature = event.features?.[0]
      const lineId =
        feature && typeof feature.properties?.line_id === 'string'
          ? feature.properties.line_id
          : null
      if (!lineId) {
        setHoveredLineId(null)
        setHoverTag(null)
        map.getCanvas().style.cursor = ''
        return
      }
      setHoveredRouteLegIndex(null)
      setHoveredLineId(lineId)
      setHoverTag({
        x: event.point.x + 12,
        y: event.point.y + 12,
        label: lineId,
      })
      map.getCanvas().style.cursor = 'pointer'
    }
    const handleNetworkMouseLeave = () => {
      setHoveredLineId(null)
      setHoverTag(null)
      map.getCanvas().style.cursor = ''
    }

    map.on('click', handleClick)
    map.on('moveend', notifyViewportBounds)
    map.on('load', () => {
      mapReadyRef.current = true
      notifyViewportBounds()

      if (!map.getSource(NETWORK_SOURCE_ID)) {
        map.addSource(NETWORK_SOURCE_ID, {
          type: 'geojson',
          data: networkLineFeaturesRef.current,
        })
      }

      if (!map.getSource(POPULATION_SOURCE_ID)) {
        map.addSource(POPULATION_SOURCE_ID, {
          type: 'geojson',
          data: populationDotFeaturesRef.current,
        })
      }

      if (!map.getLayer(POPULATION_LAYER_ID)) {
        map.addLayer({
          id: POPULATION_LAYER_ID,
          type: 'circle',
          source: POPULATION_SOURCE_ID,
          layout: {
            visibility: populationHeatmapVisibleRef.current ? 'visible' : 'none',
          },
          paint: {
            'circle-color': '#5b21b6',
            'circle-opacity': POPULATION_DOT_OPACITY,
            'circle-radius': [
              'interpolate',
              ['linear'],
              ['zoom'],
              9,
              1,
              11,
              1.5,
              13,
              2.1,
              15,
              2.8,
            ],
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': [
              'interpolate',
              ['linear'],
              ['zoom'],
              9,
              0,
              12,
              0.2,
              15,
              0.45,
            ],
          },
        })
      }

      if (!map.getLayer(NETWORK_HALO_LAYER_ID)) {
        map.addLayer({
          id: NETWORK_HALO_LAYER_ID,
          type: 'line',
          source: NETWORK_SOURCE_ID,
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 5,
            'line-opacity': 0.23,
            'line-blur': 0.6,
            'line-offset': ['coalesce', ['get', 'offset_px'], 0],
          },
        })
      }

      if (!map.getLayer(NETWORK_LAYER_ID)) {
        map.addLayer({
          id: NETWORK_LAYER_ID,
          type: 'line',
          source: NETWORK_SOURCE_ID,
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 2.75,
            'line-opacity': DEFAULT_NETWORK_LINE_OPACITY,
            'line-offset': ['coalesce', ['get', 'offset_px'], 0],
          },
        })
      }

      if (!map.getLayer(NETWORK_HOVER_LAYER_ID)) {
        map.addLayer({
          id: NETWORK_HOVER_LAYER_ID,
          type: 'line',
          source: NETWORK_SOURCE_ID,
          filter: ['==', ['get', 'line_id'], ''],
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 9,
            'line-opacity': 0.95,
            'line-blur': 1.1,
            'line-offset': ['coalesce', ['get', 'offset_px'], 0],
          },
        })
      }

      if (!map.getSource(ROUTE_SOURCE_ID)) {
        map.addSource(ROUTE_SOURCE_ID, {
          type: 'geojson',
          data: segmentFeaturesRef.current,
        })
      }

      if (!map.getLayer(ROUTE_CASING_LAYER_ID)) {
        map.addLayer({
          id: ROUTE_CASING_LAYER_ID,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          layout: {
            'line-cap': 'round',
            'line-join': 'round',
          },
          paint: {
            'line-color': '#ffffff',
            'line-width': 10,
            'line-opacity': ACTIVE_ROUTE_LINE_OPACITY,
          },
        })
      }

      if (!map.getLayer(ROUTE_LAYER_ID)) {
        map.addLayer({
          id: ROUTE_LAYER_ID,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          filter: ['==', ['get', 'style'], 'solid'],
          layout: {
            'line-cap': 'round',
            'line-join': 'round',
          },
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 5.5,
            'line-opacity': ACTIVE_ROUTE_LINE_OPACITY,
          },
        })
      }

      if (!map.getLayer(ROUTE_WALK_LAYER_ID)) {
        map.addLayer({
          id: ROUTE_WALK_LAYER_ID,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          filter: ['==', ['get', 'style'], 'walk'],
          layout: {
            'line-cap': 'round',
            'line-join': 'round',
          },
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 5.5,
            'line-opacity': ACTIVE_ROUTE_LINE_OPACITY,
            'line-dasharray': [0.8, 1.25],
          },
        })
      }

      if (!map.getLayer(ROUTE_HOVER_LAYER_ID)) {
        map.addLayer({
          id: ROUTE_HOVER_LAYER_ID,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          filter: ['==', ['get', 'leg_index'], -1],
          layout: {
            'line-cap': 'round',
            'line-join': 'round',
          },
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 9.5,
            'line-opacity': ACTIVE_ROUTE_LINE_OPACITY,
            'line-blur': 0.6,
          },
        })
      }

      if (!map.getSource(STOPS_SOURCE_ID)) {
        map.addSource(STOPS_SOURCE_ID, {
          type: 'geojson',
          data: stopFeaturesRef.current,
        })
      }

      if (!map.getLayer(STOPS_LAYER_ID)) {
        map.addLayer({
          id: STOPS_LAYER_ID,
          type: 'circle',
          source: STOPS_SOURCE_ID,
          paint: {
            'circle-radius': [
              'match',
              ['get', 'role'],
              'origin',
              8,
              'destination',
              8,
              5,
            ],
            'circle-stroke-width': 2,
            'circle-stroke-color': '#ffffff',
            'circle-color': [
              'match',
              ['get', 'role'],
              'origin',
              '#0ea5e9',
              'destination',
              '#ef4444',
              '#111827',
            ],
          },
        })
      }

      map.on('mousemove', NETWORK_LAYER_ID, handleNetworkMouseMove)
      map.on('mouseleave', NETWORK_LAYER_ID, handleNetworkMouseLeave)
      map.on('mousemove', ROUTE_LAYER_ID, handleRouteMouseMove)
      map.on('mouseleave', ROUTE_LAYER_ID, handleRouteMouseLeave)
      map.on('mousemove', ROUTE_WALK_LAYER_ID, handleRouteMouseMove)
      map.on('mouseleave', ROUTE_WALK_LAYER_ID, handleRouteMouseLeave)
    })

    return () => {
      originMarkerRef.current?.remove()
      destinationMarkerRef.current?.remove()
      mapReadyRef.current = false
      map.getCanvas().style.cursor = ''
      if (map.getLayer(NETWORK_LAYER_ID)) {
        map.off('mousemove', NETWORK_LAYER_ID, handleNetworkMouseMove)
        map.off('mouseleave', NETWORK_LAYER_ID, handleNetworkMouseLeave)
      }
      if (map.getLayer(ROUTE_LAYER_ID)) {
        map.off('mousemove', ROUTE_LAYER_ID, handleRouteMouseMove)
        map.off('mouseleave', ROUTE_LAYER_ID, handleRouteMouseLeave)
      }
      if (map.getLayer(ROUTE_WALK_LAYER_ID)) {
        map.off('mousemove', ROUTE_WALK_LAYER_ID, handleRouteMouseMove)
        map.off('mouseleave', ROUTE_WALK_LAYER_ID, handleRouteMouseLeave)
      }
      map.off('click', handleClick)
      map.off('moveend', notifyViewportBounds)
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) {
      return
    }

    if (origin) {
      if (!originMarkerRef.current) {
        originMarkerRef.current = new maplibregl.Marker({ color: '#0ea5e9' })
      }
      originMarkerRef.current.setLngLat([origin.lon, origin.lat]).addTo(map)
    } else {
      originMarkerRef.current?.remove()
    }

    if (destination) {
      if (!destinationMarkerRef.current) {
        destinationMarkerRef.current = new maplibregl.Marker({ color: '#ef4444' })
      }
      destinationMarkerRef.current.setLngLat([destination.lon, destination.lat]).addTo(map)
    } else {
      destinationMarkerRef.current?.remove()
    }
  }, [origin, destination])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReadyRef.current) {
      return
    }

    const networkSource = map.getSource(NETWORK_SOURCE_ID) as GeoJSONSource | undefined
    networkSource?.setData(networkLineFeatures)
  }, [networkLineFeatures])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReadyRef.current) {
      return
    }

    const populationSource = map.getSource(POPULATION_SOURCE_ID) as GeoJSONSource | undefined
    populationSource?.setData(populationDotFeatures ?? EMPTY_POPULATION_DOTS)
  }, [populationDotFeatures])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReadyRef.current) {
      return
    }

    const routeSource = map.getSource(ROUTE_SOURCE_ID) as GeoJSONSource | undefined
    routeSource?.setData(segmentFeatures)
  }, [segmentFeatures])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReadyRef.current) {
      return
    }

    const stopsSource = map.getSource(STOPS_SOURCE_ID) as GeoJSONSource | undefined
    stopsSource?.setData(stopFeatures)
  }, [stopFeatures])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReadyRef.current) {
      return
    }
    if (segmentFeatures.features.length === 0) {
      return
    }

    const bounds = new maplibregl.LngLatBounds()
    for (const feature of segmentFeatures.features) {
      for (const coordinate of feature.geometry.coordinates) {
        bounds.extend(coordinate as [number, number])
      }
    }
    map.fitBounds(bounds, { padding: 64, duration: 500, maxZoom: 14 })
  }, [segmentFeatures])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReadyRef.current || !map.getLayer(POPULATION_LAYER_ID)) {
      return
    }
    map.setLayoutProperty(
      POPULATION_LAYER_ID,
      'visibility',
      populationHeatmapVisible ? 'visible' : 'none'
    )
  }, [populationHeatmapVisible])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReadyRef.current || !map.getLayer(NETWORK_HOVER_LAYER_ID)) {
      return
    }
    if (!hoveredLineId) {
      map.setFilter(NETWORK_HOVER_LAYER_ID, ['==', ['get', 'line_id'], ''])
      return
    }
    map.setFilter(NETWORK_HOVER_LAYER_ID, ['==', ['get', 'line_id'], hoveredLineId])
  }, [hoveredLineId])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReadyRef.current || !map.getLayer(ROUTE_HOVER_LAYER_ID)) {
      return
    }
    if (hoveredRouteLegIndex === null) {
      map.setFilter(ROUTE_HOVER_LAYER_ID, ['==', ['get', 'leg_index'], -1])
      return
    }
    map.setFilter(ROUTE_HOVER_LAYER_ID, [
      '==',
      ['get', 'leg_index'],
      hoveredRouteLegIndex,
    ])
  }, [hoveredRouteLegIndex])

  const isHoveredLineVisible = hoveredLineId
    ? networkLineFeatures.features.some(
        (feature) => feature.properties.line_id === hoveredLineId
      )
    : false
  const isHoveredRouteLegVisible =
    hoveredRouteLegIndex !== null &&
    segmentFeatures.features.some(
      (feature) => feature.properties.leg_index === hoveredRouteLegIndex
    )
  const shouldShowHoverTag =
    hoverTag !== null && (isHoveredRouteLegVisible || isHoveredLineVisible)

  return (
    <main className="map-panel">
      <div ref={mapContainerRef} className="map-container" />
      {hoverTag && shouldShowHoverTag && (
        <div
          className="map-hover-tag"
          style={{ left: `${hoverTag.x}px`, top: `${hoverTag.y}px` }}
        >
          {hoverTag.label}
        </div>
      )}
    </main>
  )
}

export default TransitMap
