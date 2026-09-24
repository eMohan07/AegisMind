from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from aegismind_core.mcp_server import create_mcp_router
from aegismind_core.routes import CoreState, create_routes

logger = logging.getLogger(__name__)


def setup_telemetry(app: FastAPI, service_name: str = "aegismind-core") -> bool:
    """Configure OpenTelemetry instrumentation hooks if opentelemetry is available."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry instrumentation active for '%s'", service_name)
        return True
    except ImportError:
        logger.debug("OpenTelemetry packages not installed; skipping automatic instrumentation")
        return False
    except Exception as exc:
        logger.warning("Could not initialize OpenTelemetry: %s", exc)
        return False


def create_app(state: CoreState | None = None) -> FastAPI:
    """Create and configure the production FastAPI application for AegisMind."""
    app_state = state or CoreState()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("AegisMind Core application starting up")
        yield
        logger.info("AegisMind Core application shutting down")

    app = FastAPI(
        title="AegisMind Core Agora",
        description=(
            "AegisMind enterprise knowledge orchestration and "
            "permission-enforced retrieval platform"
        ),
        version="0.0.1",
        lifespan=lifespan,
    )

    # Attach state to app
    app.state.core = app_state

    # Setup CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception at %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error occurred"},
        )

    # Root redirect to OpenAPI documentation
    @app.get("/", include_in_schema=False)
    async def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    # Liveness and readiness probes
    @app.get("/healthz", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "aegismind-core"}

    @app.get("/readyz", tags=["health"])
    async def readiness_check() -> dict[str, str]:
        return {"status": "ready", "service": "aegismind-core"}

    # Include API routes
    api_router = create_routes(app_state)
    app.include_router(api_router)

    # Include MCP router
    mcp_router = create_mcp_router(pipeline=app_state.retrieval_pipeline)
    app.include_router(mcp_router)

    # Initialize OpenTelemetry hooks
    setup_telemetry(app)

    return app
