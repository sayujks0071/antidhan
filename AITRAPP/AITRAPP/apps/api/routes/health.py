"""Health check endpoints"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health response model"""

    status: str
    mode: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Health check endpoint"""
    state = request.app.state.aitrapp

    return HealthResponse(
        status="healthy",
        mode=state.mode.value,
        version="1.0.0",
    )


@router.get("/ready")
async def readiness_check(request: Request) -> dict:
    """Readiness check (for K8s)"""
    state = request.app.state.aitrapp
    system_state = state.get_system_state()

    is_ready = (
        system_state.websocket_connected
        and system_state.database_connected
        and system_state.redis_connected
    )

    return {
        "ready": is_ready,
        "websocket": system_state.websocket_connected,
        "database": system_state.database_connected,
        "redis": system_state.redis_connected,
    }

