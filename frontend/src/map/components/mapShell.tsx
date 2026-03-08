import type { RouteResponse } from '../types/route.types'
import { MapDisplay } from './mapDisplay'
import { MapStatusCard } from './mapStatusCard'

type MapShellProps = {
  isLoading: boolean
  errorMessage: string | null
  routeResult: RouteResponse | null
}

function MapShell({ isLoading, errorMessage, routeResult }: MapShellProps) {
  return (
    <main className="map-shell">
      <MapDisplay routeResult={routeResult} />

      <MapStatusCard
        isLoading={isLoading}
        errorMessage={errorMessage}
        routeResult={routeResult}
      />
    </main>
  )
}

export { MapShell }
