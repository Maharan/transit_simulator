import { legColor } from './colors'
import type { LineFamily, LineFamilyVisibility } from '../network/types'
import type { Coordinate, RouteResponse } from './types'

type RouteSidebarProps = {
  origin: Coordinate | null
  destination: Coordinate | null
  departureTime: string
  route: RouteResponse | null
  isLoading: boolean
  errorMessage: string | null
  geometryWarning: string | null
  networkLinesLoading: boolean
  networkLinesError: string | null
  lineFamilyVisibility: LineFamilyVisibility
  onLineFamilyToggle: (family: LineFamily) => void
  onDepartureTimeChange: (value: string) => void
  onReset: () => void
}

function formatCoordinate(coord: Coordinate | null): string {
  if (!coord) {
    return 'Not set'
  }
  return `${coord.lat.toFixed(6)}, ${coord.lon.toFixed(6)}`
}

function RouteSidebar({
  origin,
  destination,
  departureTime,
  route,
  isLoading,
  errorMessage,
  geometryWarning,
  networkLinesLoading,
  networkLinesError,
  lineFamilyVisibility,
  onLineFamilyToggle,
  onDepartureTimeChange,
  onReset,
}: RouteSidebarProps) {
  return (
    <aside className="sidebar">
      <header className="sidebar-header">
        <p className="eyebrow">Transit Simulator</p>
        <h1>Hamburg Router Map</h1>
        <p className="hint">
          Click once for <strong>origin</strong>, click a second time for{' '}
          <strong>destination</strong>. A third click starts a new search.
        </p>
      </header>

      <section className="selection-card">
        <div>
          <span className="selection-label">Origin</span>
          <p>{formatCoordinate(origin)}</p>
        </div>
        <div>
          <span className="selection-label">Destination</span>
          <p>{formatCoordinate(destination)}</p>
        </div>
        <div className="actions">
          <button type="button" onClick={onReset}>
            Reset
          </button>
        </div>
        <div className="time-picker">
          <label htmlFor="departure-time" className="selection-label">
            Departure time
          </label>
          <input
            id="departure-time"
            type="time"
            step={60}
            value={departureTime}
            onChange={(event) => onDepartureTimeChange(event.target.value)}
          />
        </div>
      </section>

      {isLoading && <p className="status">Routing request in progress...</p>}
      {errorMessage && <p className="status error">{errorMessage}</p>}
      {geometryWarning && <p className="status warn">{geometryWarning}</p>}

      <section className="result-card">
        <h2>Network Layers</h2>
        <p className="toggle-hint">
          Toggle permanent U-Bahn, S-Bahn, A-lines and Regional lines.
        </p>
        <div className="toggle-list">
          <label className="toggle-item">
            <input
              type="checkbox"
              checked={lineFamilyVisibility.u_bahn}
              onChange={() => onLineFamilyToggle('u_bahn')}
            />
            <span className="layer-swatch u-bahn" aria-hidden="true" />
            <span>U-Bahn</span>
          </label>
          <label className="toggle-item">
            <input
              type="checkbox"
              checked={lineFamilyVisibility.s_bahn}
              onChange={() => onLineFamilyToggle('s_bahn')}
            />
            <span className="layer-swatch s-bahn" aria-hidden="true" />
            <span>S-Bahn</span>
          </label>
          <label className="toggle-item">
            <input
              type="checkbox"
              checked={lineFamilyVisibility.a_line}
              onChange={() => onLineFamilyToggle('a_line')}
            />
            <span className="layer-swatch a-line" aria-hidden="true" />
            <span>A-lines (A1/A2/A3/A11)</span>
          </label>
          <label className="toggle-item">
            <input
              type="checkbox"
              checked={lineFamilyVisibility.regional}
              onChange={() => onLineFamilyToggle('regional')}
            />
            <span className="layer-swatch regional" aria-hidden="true" />
            <span>Regional (RE/RB)</span>
          </label>
        </div>
        {networkLinesLoading && <p className="inline-note">Loading network lines...</p>}
        {networkLinesError && <p className="inline-note error">{networkLinesError}</p>}
      </section>

      {route && (
        <>
          <section className="result-card">
            <h2>Summary</h2>
            <p>{route.itinerary.summary}</p>
            <p>{route.itinerary.timing}</p>
          </section>

          <section className="result-card">
            <h2>Context</h2>
            <ul>
              {route.context_lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>

          <section className="result-card">
            <h2>Legs</h2>
            <ul className="legs">
              {route.itinerary.legs.map((leg, index) => (
                <li key={`${leg.mode}-${leg.route ?? 'none'}-${index}`}>
                  <span
                    className="leg-dot"
                    style={{ backgroundColor: legColor(leg, index) }}
                    aria-hidden="true"
                  />
                  <span>{leg.text}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </aside>
  )
}

export default RouteSidebar
