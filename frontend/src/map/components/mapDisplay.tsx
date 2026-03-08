import { useEffect, useMemo, useRef } from 'react'
import maplibregl from 'maplibre-gl'

import './mapDisplay.css'
import {
  ENDPOINT_SOURCE_ID,
  ROUTE_SOURCE_ID,
  STOP_SOURCE_ID,
  addRouteSourcesAndLayers,
  bindRouteInteractionHandlers,
} from '../services/mapLayerConfig'
import { OSM_RASTER_STYLE } from '../services/mapStyle'
import { buildRouteMapData } from '../services/routeMapData'
import type { RouteResponse } from '../types/route.types'

type MapDisplayProps = {
  routeResult: RouteResponse | null
}

function MapDisplay({ routeResult }: MapDisplayProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const routeMapDataRef = useRef(buildRouteMapData(routeResult))

  const routeMapData = useMemo(
    () => buildRouteMapData(routeResult),
    [routeResult],
  )

  useEffect(() => {
    routeMapDataRef.current = routeMapData
  }, [routeMapData])

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

    map.on('load', () => {
      addRouteSourcesAndLayers(map)
      bindRouteInteractionHandlers(map)
      updateMapRouteData(map, routeMapDataRef.current)
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) {
      return
    }
    updateMapRouteData(map, routeMapData)
  }, [routeMapData])

  return (
    <div className="map-display">
      <div ref={mapContainerRef} className="map-canvas" />
      <div className="map-legend">
        <span className="legend-line transit" />
        <span>Transit</span>
        <span className="legend-line transfer" />
        <span>Transfer / walk</span>
      </div>
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

export { MapDisplay }
