"""API routers for ARMA."""

from arma.api.routers.chat import router as chat_router
from arma.api.routers.stream import router as stream_router

__all__ = ["chat_router", "stream_router"]
