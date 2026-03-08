import { type SyntheticEvent } from 'react'

import {
  type CoordinateField,
  type CoordinateInput,
  type Endpoint,
} from '../types/coordinates.types.ts'

type SidebarProps = {
  from: CoordinateInput
  to: CoordinateInput
  departTime: string
  canSubmit: boolean
  onCoordinateChange: (
    endpoint: Endpoint,
    field: CoordinateField,
    value: string,
  ) => void
  onDepartTimeChange: (value: string) => void
  onSubmit: () => void
  onClear: () => void
}

function Sidebar({
  from,
  to,
  departTime,
  canSubmit,
  onCoordinateChange,
  onDepartTimeChange,
  onSubmit,
  onClear,
}: SidebarProps) {
  function handleSubmit(event: SyntheticEvent<HTMLFormElement>): void {
    event.preventDefault()
    onSubmit()
  }

  return (
    <aside className="panel">
      <h1>Transit Route Planner</h1>
      <p className="panel-subtitle">
        Step 1: controlled form state and layout foundation.
      </p>

      <form className="route-form" onSubmit={handleSubmit} onReset={onClear}>
        <fieldset>
          <legend>From</legend>
          <label>
            Latitude
            <input
              type="text"
              value={from.lat}
              onChange={(event) =>
                onCoordinateChange('from', 'lat', event.target.value)
              }
              placeholder="53.549053"
            />
          </label>
          <label>
            Longitude
            <input
              type="text"
              value={from.lon}
              onChange={(event) =>
                onCoordinateChange('from', 'lon', event.target.value)
              }
              placeholder="9.989263"
            />
          </label>
        </fieldset>

        <fieldset>
          <legend>To</legend>
          <label>
            Latitude
            <input
              type="text"
              value={to.lat}
              onChange={(event) => onCoordinateChange('to', 'lat', event.target.value)}
              placeholder="53.582231"
            />
          </label>
          <label>
            Longitude
            <input
              type="text"
              value={to.lon}
              onChange={(event) => onCoordinateChange('to', 'lon', event.target.value)}
              placeholder="10.067991"
            />
          </label>
        </fieldset>

        <label>
          Departure Time (optional, HH:MM:SS)
          <input
            type="text"
            value={departTime}
            onChange={(event) => onDepartTimeChange(event.target.value)}
            placeholder="09:00:00"
          />
        </label>

        <div className="actions">
          <button type="submit" disabled={!canSubmit}>
            Route
          </button>
          <button type="reset" disabled={from.lat === '' && from.lon === '' && to.lat === '' && to.lon === ''}>
            Clear
          </button>
        </div>
      </form>
    </aside>
  )
}

export { Sidebar }
