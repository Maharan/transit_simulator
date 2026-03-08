import { useMemo, useState } from 'react'

import { MapShell } from './map/components/mapShell'
import { Sidebar } from './map/components/sidebar'
import { useRouteRequest } from './map/services/useRouteRequest'
import { isValidNumber } from './map/services/validators'
import {
  type CoordinateInput,
  type Endpoint,
  type CoordinateField,
} from './map/types/coordinates.types.ts'


function App() {
  // Form state
  const [from, setFrom] = useState<CoordinateInput>({ lat: '', lon: '' })
  const [to, setTo] = useState<CoordinateInput>({ lat: '', lon: '' })
  const [departTime, setDepartTime] = useState('')

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
        canSubmit={canSubmit}
        onCoordinateChange={handleCoordinateChange}
        onDepartTimeChange={setDepartTime}
        onSubmit={handleSubmit}
        onClear={handleReset}
      />

      <MapShell
        isLoading={isLoading}
        errorMessage={errorMessage}
        routeResult={routeResult}
      />
    </div>
  )
}

export default App
