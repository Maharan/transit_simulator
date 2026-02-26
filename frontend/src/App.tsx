import { useCallback, useEffect, useMemo, useState } from 'react'

import TransitMap from './features/map/TransitMap'
import {
  EMPTY_NETWORK_LINE_FEATURES,
  type LineFamily,
  type LineFamilyVisibility,
} from './features/network/types'
import { useNetworkLines } from './features/network/useNetworkLines'
import {
  buildSegmentFeatures,
  buildStopFeatures,
  hasAnyMissingSegmentCoordinates,
} from './features/routing/geojson'
import RouteSidebar from './features/routing/RouteSidebar'
import type { Coordinate } from './features/routing/types'
import { useRouterRoute } from './features/routing/useRouterRoute'
import './App.css'

function App() {
  const [origin, setOrigin] = useState<Coordinate | null>(null)
  const [destination, setDestination] = useState<Coordinate | null>(null)
  const [departureTime, setDepartureTime] = useState('09:00')
  const [lineFamilyVisibility, setLineFamilyVisibility] = useState<LineFamilyVisibility>({
    u_bahn: true,
    s_bahn: true,
    a_line: true,
    regional: true,
  })

  const {
    route,
    isLoading,
    errorMessage,
    requestRoute,
    cancelRequest,
    clearRoute,
    clearError,
  } = useRouterRoute()
  const {
    networkLines,
    isLoading: networkLinesLoading,
    errorMessage: networkLinesError,
    loadNetworkLines,
  } = useNetworkLines()

  useEffect(() => {
    void loadNetworkLines()
  }, [loadNetworkLines])

  useEffect(() => {
    if (!origin || !destination) {
      return
    }
    void requestRoute(origin, destination, departureTime)
  }, [origin, destination, departureTime, requestRoute])

  const segmentFeatures = useMemo(() => buildSegmentFeatures(route), [route])
  const stopFeatures = useMemo(() => buildStopFeatures(route), [route])

  const geometryWarning = useMemo(() => {
    if (!route) {
      return null
    }
    if (!hasAnyMissingSegmentCoordinates(route)) {
      return null
    }
    return (
      'Route was returned, but stop coordinates are missing in the API response. ' +
      'Restart the router container so it serves the latest backend schema.'
    )
  }, [route])

  const visibleNetworkLineFeatures = useMemo(() => {
    if (!networkLines) {
      return EMPTY_NETWORK_LINE_FEATURES
    }
    const visibleFeatures = networkLines.features.filter((feature) => {
      const family = feature.properties?.line_family
      if (
        family !== 'u_bahn' &&
        family !== 's_bahn' &&
        family !== 'a_line' &&
        family !== 'regional'
      ) {
        return false
      }
      return lineFamilyVisibility[family]
    })
    return {
      type: 'FeatureCollection' as const,
      features: visibleFeatures,
    }
  }, [lineFamilyVisibility, networkLines])

  const handleMapClick = useCallback(
    (point: Coordinate) => {
      clearError()
      clearRoute()

      if (!origin || destination) {
        setOrigin(point)
        setDestination(null)
        return
      }
      setDestination(point)
    },
    [clearError, clearRoute, destination, origin]
  )

  const handleReset = useCallback(() => {
    cancelRequest()
    clearError()
    clearRoute()
    setOrigin(null)
    setDestination(null)
  }, [cancelRequest, clearError, clearRoute])

  const handleLineFamilyToggle = useCallback((family: LineFamily) => {
    setLineFamilyVisibility((current) => ({
      ...current,
      [family]: !current[family],
    }))
  }, [])

  return (
    <div className="app-shell">
      <RouteSidebar
        origin={origin}
        destination={destination}
        departureTime={departureTime}
        route={route}
        isLoading={isLoading}
        errorMessage={errorMessage}
        geometryWarning={geometryWarning}
        networkLinesLoading={networkLinesLoading}
        networkLinesError={networkLinesError}
        lineFamilyVisibility={lineFamilyVisibility}
        onLineFamilyToggle={handleLineFamilyToggle}
        onDepartureTimeChange={setDepartureTime}
        onReset={handleReset}
      />
      <TransitMap
        origin={origin}
        destination={destination}
        networkLineFeatures={visibleNetworkLineFeatures}
        segmentFeatures={segmentFeatures}
        stopFeatures={stopFeatures}
        onMapClick={handleMapClick}
      />
    </div>
  )
}

export default App
