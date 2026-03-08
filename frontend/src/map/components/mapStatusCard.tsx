import type { RouteResponse } from '../types/route.types'

type MapStatusCardProps = {
  isLoading: boolean
  errorMessage: string | null
  routeResult: RouteResponse | null
}

function MapStatusCard({
  isLoading,
  errorMessage,
  routeResult,
}: MapStatusCardProps) {
  return (
    <section className="map-status-card">
      {isLoading && <p>Loading route...</p>}

      {!isLoading && errorMessage && (
        <>
          <p className="status-title">Route request failed</p>
          <p>{errorMessage}</p>
        </>
      )}

      {!isLoading && !errorMessage && routeResult && (
        <>
          <p className="status-title">Latest Route Result</p>
          <p>{routeResult.itinerary.summary}</p>
          <p>{routeResult.itinerary.timing}</p>
          {routeResult.itinerary.legs.length > 0 && (
            <ul>
              {routeResult.itinerary.legs.map((leg, index) => (
                <li key={`${leg.mode}-${index}`}>{leg.text}</li>
              ))}
            </ul>
          )}
        </>
      )}

      {!isLoading && !errorMessage && !routeResult && (
        <p>Submit a route request to see itinerary results here.</p>
      )}
    </section>
  )
}

export { MapStatusCard }
