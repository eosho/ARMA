"""FastAPI application for ARMA."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from arma.__version__ import get_version
from arma.api.models import HealthResponse
from arma.api.routers import chat_router
from arma.core.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # pylint: disable=unused-argument
    """Application lifespan manager."""
    logger.info("Starting ARMA API server")
    yield
    logger.info("Shutting down ARMA API server")


# Create FastAPI app
app = FastAPI(
    title="ARMA API",
    description="Azure Resource Management Assistant - AI-powered Azure deployment agent",
    version=get_version(),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat_router)


@app.get("/", response_model=HealthResponse)
async def root() -> HealthResponse:
    """Root endpoint - health check."""
    return HealthResponse(status="healthy", version=get_version())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "arma.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
