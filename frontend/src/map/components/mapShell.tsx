import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'

import type { SelectedCoordinatePoint } from '../types/coordinates.types'
import type { RouteResponse } from '../types/route.types'
import { MapDisplay } from './mapDisplay'
import { MapStatusCard } from './mapStatusCard'

const DEFAULT_MAP_PANE_RATIO = 0.68
const MIN_MAP_PANE_PX = 260
const MIN_STATUS_PANE_PX = 170

function clampMapPaneRatio(nextRatio: number, totalHeight: number): number {
  if (totalHeight <= 0) {
    return nextRatio
  }

  const minRatio = MIN_MAP_PANE_PX / totalHeight
  const maxRatio = 1 - MIN_STATUS_PANE_PX / totalHeight

  if (minRatio > maxRatio) {
    const fallbackRatio =
      MIN_MAP_PANE_PX / (MIN_MAP_PANE_PX + MIN_STATUS_PANE_PX)
    const lowerBound = Math.max(0.42, fallbackRatio - 0.1)
    const upperBound = Math.min(0.78, fallbackRatio + 0.1)
    return Math.min(Math.max(nextRatio, lowerBound), upperBound)
  }

  return Math.min(Math.max(nextRatio, minRatio), maxRatio)
}

type MapShellProps = {
  isLoading: boolean
  errorMessage: string | null
  routeResult: RouteResponse | null
  selectedRouteOptionIndex: number | null
  showPopulationHeatmap: boolean
  showRapidTransitLines: boolean
  selectedFromPoint: SelectedCoordinatePoint | null
  selectedToPoint: SelectedCoordinatePoint | null
  onMapCoordinateSelect: (point: SelectedCoordinatePoint) => void
  onRouteOptionSelect: (optionIndex: number | null) => void
}

function MapShell({
  isLoading,
  errorMessage,
  routeResult,
  selectedRouteOptionIndex,
  showPopulationHeatmap,
  showRapidTransitLines,
  selectedFromPoint,
  selectedToPoint,
  onMapCoordinateSelect,
  onRouteOptionSelect,
}: MapShellProps) {
  const panelsRef = useRef<HTMLDivElement | null>(null)
  const dragStateRef = useRef<{ pointerId: number } | null>(null)
  const [mapPaneRatio, setMapPaneRatio] = useState(DEFAULT_MAP_PANE_RATIO)
  const [isResizing, setIsResizing] = useState(false)
  const routeStatusCardKey = routeResult
    ? [
        routeResult.feed_id,
        routeResult.best_plan.arrival_time_sec,
        routeResult.best_option_index,
        routeResult.options
          .map(
            (option) =>
              `${option.best_plan.arrival_time_sec}-${option.major_trip_transfers}`,
          )
          .join('|'),
      ].join(':')
    : 'route-empty'

  function updateMapPaneRatioFromPointer(clientY: number): void {
    const panels = panelsRef.current
    if (!panels) {
      return
    }

    const bounds = panels.getBoundingClientRect()
    if (bounds.height <= 0) {
      return
    }

    const rawRatio = (clientY - bounds.top) / bounds.height
    setMapPaneRatio(clampMapPaneRatio(rawRatio, bounds.height))
  }

  useEffect(() => {
    if (!isResizing) {
      return
    }

    const handlePointerMove = (event: PointerEvent) => {
      if (
        dragStateRef.current === null ||
        event.pointerId !== dragStateRef.current.pointerId
      ) {
        return
      }

      const panels = panelsRef.current
      if (!panels) {
        return
      }

      const bounds = panels.getBoundingClientRect()
      if (bounds.height <= 0) {
        return
      }

      const rawRatio = (event.clientY - bounds.top) / bounds.height
      setMapPaneRatio(clampMapPaneRatio(rawRatio, bounds.height))
    }

    const handlePointerUp = (event: PointerEvent) => {
      if (
        dragStateRef.current === null ||
        event.pointerId !== dragStateRef.current.pointerId
      ) {
        return
      }
      dragStateRef.current = null
      setIsResizing(false)
    }

    document.body.classList.add('is-map-shell-resizing')
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
    window.addEventListener('pointercancel', handlePointerUp)

    return () => {
      document.body.classList.remove('is-map-shell-resizing')
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
      window.removeEventListener('pointercancel', handlePointerUp)
    }
  }, [isResizing])

  const mapPanePercent = `${(mapPaneRatio * 100).toFixed(2)}%`
  const statusPanePercent = `${((1 - mapPaneRatio) * 100).toFixed(2)}%`

  function handleResizePointerDown(
    event: ReactPointerEvent<HTMLButtonElement>,
  ): void {
    event.preventDefault()
    dragStateRef.current = { pointerId: event.pointerId }
    setIsResizing(true)
    updateMapPaneRatioFromPointer(event.clientY)
  }

  function handleResizeKeyDown(
    event: ReactKeyboardEvent<HTMLButtonElement>,
  ): void {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') {
      return
    }

    event.preventDefault()
    const delta = event.key === 'ArrowUp' ? 0.04 : -0.04
    setMapPaneRatio((currentRatio) => {
      const panels = panelsRef.current
      if (!panels) {
        return currentRatio
      }

      const totalHeight = panels.getBoundingClientRect().height
      return clampMapPaneRatio(currentRatio + delta, totalHeight)
    })
  }

  return (
    <main className="map-shell">
      <div ref={panelsRef} className="map-shell-panels">
        <section
          className="map-shell-pane map-shell-pane--map"
          style={{ flexBasis: mapPanePercent }}
        >
          <MapDisplay
            routeResult={routeResult}
            selectedRouteOptionIndex={selectedRouteOptionIndex}
            showPopulationHeatmap={showPopulationHeatmap}
            showRapidTransitLines={showRapidTransitLines}
            selectedFromPoint={selectedFromPoint}
            selectedToPoint={selectedToPoint}
            onMapCoordinateSelect={onMapCoordinateSelect}
          />
        </section>

        <button
          type="button"
          className={`map-shell-resizer${isResizing ? ' map-shell-resizer--active' : ''}`}
          aria-label="Resize map and itinerary panels"
          aria-orientation="horizontal"
          onPointerDown={handleResizePointerDown}
          onKeyDown={handleResizeKeyDown}
        >
          <span className="map-shell-resizer-line" />
        </button>

        <section
          className="map-shell-pane map-shell-pane--status"
          style={{ flexBasis: statusPanePercent }}
        >
          <MapStatusCard
            key={routeStatusCardKey}
            isLoading={isLoading}
            errorMessage={errorMessage}
            routeResult={routeResult}
            selectedRouteOptionIndex={selectedRouteOptionIndex}
            selectedFromPoint={selectedFromPoint}
            selectedToPoint={selectedToPoint}
            onRouteOptionSelect={onRouteOptionSelect}
          />
        </section>
      </div>
    </main>
  )
}

export { MapShell }
