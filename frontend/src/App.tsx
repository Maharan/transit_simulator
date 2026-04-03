import { useEffect, useMemo, useState } from 'react'

import { MapShell } from './map/components/mapShell'
import { Sidebar } from './map/components/sidebar'
import { useRouteRequest } from './map/services/useRouteRequest'
import { isValidNumber } from './map/services/validators'
import {
  type CoordinateInput,
  type Endpoint,
  type CoordinateField,
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

  const canSubmit = fromValid && toValid
  const isDarkMode = themeMode === 'dark'

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode)
  }, [themeMode])

  function handleCoordinateChange(
    endpoint: Endpoint,
    field: CoordinateField,
    value: string,
  ): void {
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
    resetRouteRequest()
  }

  function handleSubmit(): void {
    if (!canSubmit) {
      return
    }
    const payload = {
      from_lat: Number(from.lat),
      from_lon: Number(from.lon),
      to_lat: Number(to.lat),
      to_lon: Number(to.lon),
      depart_time: departTime.trim() || undefined,
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
        showPopulationHeatmap={showPopulationHeatmap}
        showRapidTransitLines={showRapidTransitLines}
      />
    </div>
  )
}

export default App
