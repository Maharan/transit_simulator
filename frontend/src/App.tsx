import { useEffect, useMemo, useState } from 'react'

import { MapShell } from './map/components/mapShell'
import { Sidebar } from './map/components/sidebar'
import { getBestRouteOptionIndex } from './map/services/routeOptions'
import { useRouteRequest } from './map/services/useRouteRequest'
import { isValidNumber } from './map/services/validators'
import {
  type CoordinateInput,
  type Endpoint,
  type CoordinateField,
  type SelectedCoordinatePoint,
} from './map/types/coordinates.types.ts'

const THEME_STORAGE_KEY = 'transit-simulator-theme'

type ThemeMode = 'light' | 'dark'

function getInitialThemeMode(): ThemeMode {
  if (typeof window === 'undefined') {
    return 'light'
  }

  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (storedTheme === 'light' || storedTheme === 'dark') {
    return storedTheme
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

function App() {
  // Form state
  const [from, setFrom] = useState<CoordinateInput>({ lat: '', lon: '' })
  const [to, setTo] = useState<CoordinateInput>({ lat: '', lon: '' })
  const [departTime, setDepartTime] = useState('')
  const [themeMode, setThemeMode] = useState<ThemeMode>(getInitialThemeMode)
  const [showPopulationHeatmap, setShowPopulationHeatmap] = useState(false)
  const [showRapidTransitLines, setShowRapidTransitLines] = useState(true)
  const [preferredRouteOptionIndex, setPreferredRouteOptionIndex] = useState<number | null>(null)

  // Route request state
  const {
    isLoading,
    errorMessage,
    routeResult,
    submitRoute,
    resetRouteRequest,
  } = useRouteRequest()

  const fromValid = useMemo(() => {
    return isValidNumber(from.lat) && isValidNumber(from.lon)
  }, [from])

  const toValid = useMemo(() => {
    return isValidNumber(to.lat) && isValidNumber(to.lon)
  }, [to])

  const selectedFromPoint = useMemo(
    () => parseSelectedCoordinatePoint(from),
    [from],
  )
  const selectedToPoint = useMemo(
    () => parseSelectedCoordinatePoint(to),
    [to],
  )

  const canSubmit = fromValid && toValid
  const isDarkMode = themeMode === 'dark'
  const selectedRouteOptionIndex = useMemo(() => {
    if (!routeResult) {
      return null
    }

    const bestRouteOptionIndex = getBestRouteOptionIndex(routeResult)
    if (preferredRouteOptionIndex === null) {
      return bestRouteOptionIndex
    }

    if (
      preferredRouteOptionIndex < 0 ||
      preferredRouteOptionIndex >= routeResult.options.length
    ) {
      return bestRouteOptionIndex
    }

    return preferredRouteOptionIndex
  }, [preferredRouteOptionIndex, routeResult])

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode)
  }, [themeMode])

  function handleCoordinateChange(
    endpoint: Endpoint,
    field: CoordinateField,
    value: string,
  ): void {
    setPreferredRouteOptionIndex(null)
    resetRouteRequest()
    if (endpoint === 'from') {
      setFrom((prev) => ({ ...prev, [field]: value }))
      return
    }
    setTo((prev) => ({ ...prev, [field]: value }))
  }

  function handleReset(): void {
    setFrom({ lat: '', lon: '' })
    setTo({ lat: '', lon: '' })
    setDepartTime('')
    setPreferredRouteOptionIndex(null)
    resetRouteRequest()
  }

  function handleSubmit(): void {
    if (!canSubmit) {
      return
    }
    const payload = buildRoutePayload({
      from: selectedFromPoint,
      to: selectedToPoint,
      departTime,
    })
    if (!payload) {
      return
    }
    setPreferredRouteOptionIndex(null)
    void submitRoute(payload)
  }

  function handleMapCoordinateSelect(point: SelectedCoordinatePoint): void {
    const pointInput = formatCoordinateInput(point)
    if (!selectedFromPoint || (selectedFromPoint && selectedToPoint)) {
      setPreferredRouteOptionIndex(null)
      resetRouteRequest()
      setFrom(pointInput)
      setTo({ lat: '', lon: '' })
      return
    }

    const nextTargetInput = pointInput
    const nextTargetPoint = parseSelectedCoordinatePoint(nextTargetInput)
    if (!nextTargetPoint) {
      return
    }

    setPreferredRouteOptionIndex(null)
    resetRouteRequest()
    setTo(nextTargetInput)
    const payload = buildRoutePayload({
      from: selectedFromPoint,
      to: nextTargetPoint,
      departTime,
    })
    if (!payload) {
      return
    }
    void submitRoute(payload)
  }

  return (
    <div className="app">
      <Sidebar
        from={from}
        to={to}
        departTime={departTime}
        isDarkMode={isDarkMode}
        showPopulationHeatmap={showPopulationHeatmap}
        showRapidTransitLines={showRapidTransitLines}
        canSubmit={canSubmit}
        onCoordinateChange={handleCoordinateChange}
        onDepartTimeChange={setDepartTime}
        onDarkModeToggle={(value) => setThemeMode(value ? 'dark' : 'light')}
        onPopulationHeatmapToggle={setShowPopulationHeatmap}
        onRapidTransitLinesToggle={setShowRapidTransitLines}
        onSubmit={handleSubmit}
        onClear={handleReset}
      />

      <MapShell
        isLoading={isLoading}
        errorMessage={errorMessage}
        routeResult={routeResult}
        selectedRouteOptionIndex={selectedRouteOptionIndex}
        showPopulationHeatmap={showPopulationHeatmap}
        showRapidTransitLines={showRapidTransitLines}
        selectedFromPoint={selectedFromPoint}
        selectedToPoint={selectedToPoint}
        onMapCoordinateSelect={handleMapCoordinateSelect}
        onRouteOptionSelect={setPreferredRouteOptionIndex}
      />
    </div>
  )
}

function parseSelectedCoordinatePoint(
  input: CoordinateInput,
): SelectedCoordinatePoint | null {
  if (!isValidNumber(input.lat) || !isValidNumber(input.lon)) {
    return null
  }

  return {
    lat: Number(input.lat),
    lon: Number(input.lon),
  }
}

function formatCoordinateInput(
  point: SelectedCoordinatePoint,
): CoordinateInput {
  return {
    lat: point.lat.toFixed(6),
    lon: point.lon.toFixed(6),
  }
}

function buildRoutePayload({
  from,
  to,
  departTime,
}: {
  from: SelectedCoordinatePoint | null
  to: SelectedCoordinatePoint | null
  departTime: string
}) {
  if (!from || !to) {
    return null
  }

  return {
    from_lat: from.lat,
    from_lon: from.lon,
    to_lat: to.lat,
    to_lon: to.lon,
    depart_time: departTime.trim() || undefined,
    graph_method: 'raptor',
    max_major_transfers: 4,
  }
}

export default App
