from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware

from .route_service import RouteService
from .serializers import (
    HealthResponse,
    NetworkLineFeatureCollectionResponse,
    PopulationGridFeatureCollectionResponse,
    ReloadGraphRequest,
    ReloadGraphResponse,
    RouteRequest,
    RouteResponse,
)


def build_fastapi_app(service: RouteService) -> FastAPI:
    app = FastAPI(title="Transit Route Service")
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse.model_validate(service.status())

    @app.post("/route", response_model=RouteResponse)
    def route(request: RouteRequest) -> RouteResponse:
        try:
            return RouteResponse.model_validate(service.route(request))
        except SystemExit as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive guardrail.
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/reload-graph", response_model=ReloadGraphResponse)
    def reload_graph(request: ReloadGraphRequest) -> ReloadGraphResponse:
        try:
            return ReloadGraphResponse(
                cache_logs=service.preload(rebuild=request.rebuild)
            )
        except SystemExit as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive guardrail.
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/network-lines", response_model=NetworkLineFeatureCollectionResponse)
    def network_lines(
        feed_id: str | None = None,
    ) -> NetworkLineFeatureCollectionResponse:
        try:
            return NetworkLineFeatureCollectionResponse.model_validate(
                service.network_lines(feed_id=feed_id)
            )
        except SystemExit as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive guardrail.
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/population-grid", response_model=PopulationGridFeatureCollectionResponse)
    def population_grid(
        dataset_year: int = 2020,
        min_lat: float | None = None,
        min_lon: float | None = None,
        max_lat: float | None = None,
        max_lon: float | None = None,
    ) -> PopulationGridFeatureCollectionResponse:
        try:
            return PopulationGridFeatureCollectionResponse.model_validate(
                service.population_grid(
                    dataset_year=dataset_year,
                    min_lat=min_lat,
                    min_lon=min_lon,
                    max_lat=max_lat,
                    max_lon=max_lon,
                )
            )
        except SystemExit as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive guardrail.
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app
