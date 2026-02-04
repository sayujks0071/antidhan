"""Debug endpoints for testing and diagnostics"""
import time

import structlog
from fastapi import APIRouter, HTTPException

from apps.api.main import app_state

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post("/debug/scan-once")
async def scan_once():
    """Manually trigger one scan cycle and update heartbeat"""
    from packages.core.heartbeats import touch_scan

    if not app_state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    t0 = time.perf_counter()
    try:
        await app_state.orchestrator._scan_cycle()
    except Exception as e:
        logger.error(f"Scan cycle error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scan cycle failed: {str(e)}")
    finally:
        touch_scan()

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "status": "success",
        "elapsed_ms": elapsed_ms,
        "message": "Scan cycle completed and heartbeat updated"
    }

