"""Debug endpoints for supervisor control and inspection"""
import structlog
from fastapi import APIRouter, HTTPException

from apps.api.main import app_state
from packages.core.metrics import (
    scan_interval_seconds,
    scan_supervisor_state,
    scan_ticks_total,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


def get_gauge_value(gauge):
    """Get current gauge value from Prometheus gauge"""
    samples = list(gauge._samples())
    if samples:
        return samples[0].value
    return 0.0


@router.get("/debug/supervisor/status")
async def supervisor_status():
    """Get supervisor status"""
    return {
        "state": int(get_gauge_value(scan_supervisor_state)),
        "state_label": {
            0: "stopped",
            1: "running",
            2: "done",
            3: "exception",
            4: "stopping"
        }.get(int(get_gauge_value(scan_supervisor_state)), "unknown"),
        "ticks": int(get_gauge_value(scan_ticks_total)),
        "interval_s": get_gauge_value(scan_interval_seconds),
    }


@router.post("/debug/supervisor/start")
async def supervisor_start():
    """Manually start the supervisor"""
    if not app_state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        await app_state.orchestrator.start()
        return await supervisor_status()
    except Exception as e:
        logger.error(f"Failed to start supervisor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start supervisor: {str(e)}")


@router.post("/debug/supervisor/stop")
async def supervisor_stop():
    """Manually stop the supervisor"""
    if not app_state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        await app_state.orchestrator.stop()
        return await supervisor_status()
    except Exception as e:
        logger.error(f"Failed to stop supervisor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop supervisor: {str(e)}")

