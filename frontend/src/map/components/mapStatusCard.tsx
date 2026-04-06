import { useMemo, useState } from 'react'

import { getBestRouteOptionIndex, getRouteOptions } from '../services/routeOptions'
import type { SelectedCoordinatePoint } from '../types/coordinates.types'
import type {
  LegResponse,
  RouteOptionResponse,
  RouteResponse,
} from '../types/route.types'

type MapStatusCardProps = {
  isLoading: boolean
  errorMessage: string | null
  routeResult: RouteResponse | null
  selectedRouteOptionIndex: number | null
  selectedFromPoint: SelectedCoordinatePoint | null
  selectedToPoint: SelectedCoordinatePoint | null
  onRouteOptionSelect: (optionIndex: number | null) => void
}

function MapStatusCard({
  isLoading,
  errorMessage,
  routeResult,
  selectedRouteOptionIndex,
  selectedFromPoint,
  selectedToPoint,
  onRouteOptionSelect,
}: MapStatusCardProps) {
  const routeOptions = useMemo(() => getRouteOptions(routeResult), [routeResult])
  const bestOptionIndex = useMemo(
    () => getBestRouteOptionIndex(routeResult),
    [routeResult],
  )
  const fewestTransferCount = useMemo(
    () =>
      routeOptions.reduce(
        (lowestTransferCount, option) =>
          Math.min(lowestTransferCount, option.major_trip_transfers),
        Number.POSITIVE_INFINITY,
      ),
    [routeOptions],
  )
  const [expandedOptionState, setExpandedOptionState] = useState<
    number | 'collapsed'
  >(bestOptionIndex)
  const expandedOptionIndex =
    expandedOptionState === 'collapsed' ? null : expandedOptionState

  function handleOptionToggle(optionIndex: number): void {
    onRouteOptionSelect(optionIndex)
    setExpandedOptionState((currentIndex) =>
      currentIndex === optionIndex ? 'collapsed' : optionIndex,
    )
  }

  return (
    <section
      className="map-status-card"
      role="region"
      tabIndex={0}
      aria-label="Route status and itinerary"
    >
      {isLoading && <p>Loading route...</p>}

      {!isLoading && errorMessage && (
        <>
          <p className="status-title">Route request failed</p>
          <p>{errorMessage}</p>
        </>
      )}

      {!isLoading && !errorMessage && routeResult && (
        <>
          <p className="status-title">
            {routeOptions.length > 1 ? 'Route Options' : 'Latest Route Result'}
          </p>
          {routeOptions.length > 1 && (
            <p>{`${routeOptions.length} Pareto-optimal transit options.`}</p>
          )}
          {routeOptions.length <= 1 && routeOptions[0] && (
            <RouteOptionDetails option={routeOptions[0]} />
          )}
          {routeOptions.length > 1 && (
            <div className="route-options" aria-label="Route options">
              {routeOptions.map((option, index) => {
                const isExpanded = expandedOptionIndex === index
                const isSelected = selectedRouteOptionIndex === index
                const isBestOption = bestOptionIndex === index
                const hasFewestTransfers =
                  option.major_trip_transfers === fewestTransferCount

                return (
                  <article
                    key={`route-option-${index}`}
                    className={`route-option${isSelected ? ' route-option--selected' : ''}`}
                  >
                    <button
                      type="button"
                      className="route-option-button"
                      aria-expanded={isExpanded}
                      onClick={() => handleOptionToggle(index)}
                    >
                      <span className="route-option-header">
                        <span className="route-option-heading">
                          <span className="route-option-title">{`Option ${index + 1}`}</span>
                        </span>
                        <span className="route-option-flags">
                          {isSelected && (
                            <span className="route-option-pill route-option-pill--selected">
                              Shown on map
                            </span>
                          )}
                          {isBestOption && (
                            <span className="route-option-pill route-option-pill--arrival">
                              Earliest arrival
                            </span>
                          )}
                          {hasFewestTransfers && (
                            <span className="route-option-pill route-option-pill--transfer">
                              Fewest transfers
                            </span>
                          )}
                        </span>
                        <span className="route-option-metrics">
                          <span className="route-option-metric">
                            {`Arrive ${formatClockTime(
                              option.best_plan.arrival_time_sec,
                            )}`}
                          </span>
                          <span className="route-option-metric">
                            {formatTransferSummary(option)}
                          </span>
                        </span>
                      </span>
                      <span
                        className={`route-option-chevron${
                          isExpanded ? ' route-option-chevron--open' : ''
                        }`}
                        aria-hidden="true"
                      >
                        ^
                      </span>
                    </button>
                    {isExpanded && (
                      <div className="route-option-details">
                        <RouteOptionDetails option={option} />
                      </div>
                    )}
                  </article>
                )
              })}
            </div>
          )}
        </>
      )}

      {!isLoading && !errorMessage && !routeResult && (
        <>
          <p className="status-title">Map Click Routing</p>
          {!selectedFromPoint && (
            <p>Click the map once to place the route origin.</p>
          )}
          {selectedFromPoint && !selectedToPoint && (
            <>
              <p>{`Origin selected at ${formatPoint(selectedFromPoint)}.`}</p>
              <p>Click a second point on the map to request the route.</p>
            </>
          )}
          {selectedFromPoint && selectedToPoint && (
            <p>{`Selected ${formatPoint(selectedFromPoint)} -> ${formatPoint(selectedToPoint)}.`}</p>
          )}
        </>
      )}
    </section>
  )
}

function RouteOptionDetails({
  option,
}: {
  option: RouteOptionResponse
}) {
  return (
    <>
      <p>{option.itinerary.summary}</p>
      <p>{option.itinerary.timing}</p>
      {option.itinerary.legs.length > 0 && (
        <div className="route-timeline" aria-label="Route legs">
          {option.itinerary.legs.map((leg, index) =>
            isConnectorLeg(leg.mode) ? (
              <div
                key={`${leg.mode}-${index}`}
                className="route-leg route-leg--connector"
              >
                <div className="route-leg-rail" aria-hidden="true">
                  <span className="route-leg-dash" />
                </div>
                <div className="route-leg-connector-copy">
                  <div className="route-leg-connector-title">
                    {buildConnectorTitle(leg)}
                  </div>
                  <div className="route-leg-copy">{buildLegPathLabel(leg)}</div>
                </div>
              </div>
            ) : (
              <div
                key={`${leg.mode}-${index}`}
                className="route-leg route-leg--ride"
              >
                <div className="route-leg-rail" aria-hidden="true">
                  <span className="route-leg-dot" />
                </div>
                <div className="route-leg-card">
                  <div className="route-leg-card-header">
                    <span className="route-leg-badge">{leg.route || 'Ride'}</span>
                    <span className="route-leg-duration">
                      {formatDuration(leg.duration_sec)}
                    </span>
                  </div>
                  <div className="route-leg-title">
                    {leg.route ? `Ride ${leg.route}` : 'Transit ride'}
                  </div>
                  <div className="route-leg-copy">{buildLegPathLabel(leg)}</div>
                </div>
              </div>
            ),
          )}
        </div>
      )}
    </>
  )
}

function formatPoint(point: SelectedCoordinatePoint): string {
  return `${point.lat.toFixed(6)}, ${point.lon.toFixed(6)}`
}

function isConnectorLeg(mode: string): boolean {
  return mode !== 'ride'
}

function buildConnectorTitle(leg: LegResponse): string {
  const modeLabel =
    leg.mode === 'walk'
      ? 'Walk'
      : leg.mode === 'station_link'
        ? 'Station transfer'
        : leg.mode === 'transfer'
          ? 'Transfer'
          : startCase(leg.mode)

  const durationLabel = formatDuration(leg.duration_sec)
  return durationLabel === 'n/a'
    ? modeLabel
    : `${modeLabel} - ${durationLabel}`
}

function buildLegPathLabel(leg: LegResponse): string {
  const fromStop = leg.from_stop || 'Origin'
  const toStop = leg.to_stop || 'Destination'
  return `${fromStop} -> ${toStop}`
}

function formatDuration(durationSec: number | null): string {
  if (durationSec === null) {
    return 'n/a'
  }

  if (durationSec < 60) {
    return `${durationSec}s`
  }

  if (durationSec < 3600) {
    return `${Math.round(durationSec / 60)} min`
  }

  const hours = Math.floor(durationSec / 3600)
  const minutes = Math.round((durationSec % 3600) / 60)
  if (minutes === 0) {
    return `${hours} hr`
  }
  return `${hours} hr ${minutes} min`
}

function formatClockTime(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600) % 24
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return [hours, minutes, seconds]
    .map((value) => value.toString().padStart(2, '0'))
    .join(':')
}

function formatTransferSummary(option: RouteOptionResponse): string {
  const transferLabel =
    option.major_trip_transfers === 1 ? 'transfer' : 'transfers'
  const legLabel = option.transit_legs === 1 ? 'ride leg' : 'ride legs'
  return `${option.major_trip_transfers} ${transferLabel} | ${option.transit_legs} ${legLabel}`
}

function startCase(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export { MapStatusCard }
