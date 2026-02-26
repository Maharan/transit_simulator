from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .route_service import RouteService
from .serializers import (
    HealthResponse,
    NetworkLineFeatureCollectionResponse,
    ReloadGraphRequest,
    ReloadGraphResponse,
    RouteRequest,
    RouteResponse,
)


def build_fastapi_app(service: RouteService) -> FastAPI:
    app = FastAPI(title="Transit Route Service")

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

    return app
