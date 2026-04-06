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
  isDarkMode: boolean
  showPopulationHeatmap: boolean
  showRapidTransitLines: boolean
  canSubmit: boolean
  onCoordinateChange: (
    endpoint: Endpoint,
    field: CoordinateField,
    value: string,
  ) => void
  onDepartTimeChange: (value: string) => void
  onDarkModeToggle: (value: boolean) => void
  onPopulationHeatmapToggle: (value: boolean) => void
  onRapidTransitLinesToggle: (value: boolean) => void
  onSubmit: () => void
  onClear: () => void
}

function Sidebar({
  from,
  to,
  departTime,
  isDarkMode,
  showPopulationHeatmap,
  showRapidTransitLines,
  canSubmit,
  onCoordinateChange,
  onDepartTimeChange,
  onDarkModeToggle,
  onPopulationHeatmapToggle,
  onRapidTransitLinesToggle,
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
        Click the map to place the origin, click again to place the destination,
        and click a third time to reset the selection.
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
          <small className="field-hint">
            Filled automatically from the first map click, but still editable.
          </small>
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
          <small className="field-hint">
            Filled automatically from the second map click and routed immediately.
          </small>
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

        <fieldset>
          <legend>Map Layers</legend>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={showRapidTransitLines}
              onChange={(event) =>
                onRapidTransitLinesToggle(event.target.checked)
              }
            />
            <span>
              S-Bahn / U-Bahn Lines
              <small>
                Static rapid-transit network overlay using the backend line
                geometry and colors.
              </small>
            </span>
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={showPopulationHeatmap}
              onChange={(event) =>
                onPopulationHeatmapToggle(event.target.checked)
              }
            />
            <span>
              Population Surface
              <small>Fixed-color floor-space density grid scaled to 1.85 million residents.</small>
            </span>
          </label>
        </fieldset>

        <fieldset>
          <legend>Appearance</legend>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={isDarkMode}
              onChange={(event) => onDarkModeToggle(event.target.checked)}
            />
            <span>
              Dark Mode
              <small>
                Switch the planner panels, legends, and map popups to a darker
                theme.
              </small>
            </span>
          </label>
        </fieldset>

        <div className="actions">
          <button type="submit" disabled={!canSubmit}>
            Route
          </button>
          <button
            type="reset"
            disabled={
              from.lat === '' &&
              from.lon === '' &&
              to.lat === '' &&
              to.lon === '' &&
              departTime === ''
            }
          >
            Clear
          </button>
        </div>
      </form>
    </aside>
  )
}

export { Sidebar }
