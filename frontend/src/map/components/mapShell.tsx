import type { RouteResponse } from '../types/route.types'
import { MapDisplay } from './mapDisplay'
import { MapStatusCard } from './mapStatusCard'

type MapShellProps = {
  isLoading: boolean
  errorMessage: string | null
  routeResult: RouteResponse | null
  showPopulationHeatmap: boolean
  showRapidTransitLines: boolean
}

function MapShell({
  isLoading,
  errorMessage,
  routeResult,
  showPopulationHeatmap,
  showRapidTransitLines,
}: MapShellProps) {
  return (
    <main className="map-shell">
      <MapDisplay
        routeResult={routeResult}
        showPopulationHeatmap={showPopulationHeatmap}
        showRapidTransitLines={showRapidTransitLines}
      />

      <MapStatusCard
        isLoading={isLoading}
        errorMessage={errorMessage}
        routeResult={routeResult}
      />
    </main>
  )
}

export { MapShell }
