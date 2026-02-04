"""Incident snapshot generator"""
import json
from datetime import datetime
from pathlib import Path

import structlog

from packages.core.config import app_config, settings
from packages.storage.database import get_db_session
from packages.storage.models import AuditLog, Position, RiskEvent

logger = structlog.get_logger(__name__)


def snapshot_incident(incident_type: str, details: dict) -> str:
    """
    Create incident snapshot on risk event.
    
    Args:
        incident_type: Type of incident (e.g., "RISK_EVENT", "KILL_SWITCH")
        details: Incident details
    
    Returns:
        Path to snapshot directory
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = Path(f"reports/incident-{timestamp}")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    logger.critical("Creating incident snapshot",
                   incident_type=incident_type,
                   snapshot_dir=str(snapshot_dir))

    # 1. Current config
    config_data = {
        "config_sha": getattr(app_config, 'config_sha', 'unknown'),
        "mode": settings.app_mode.value,
        "timestamp": datetime.now().isoformat()
    }
    with open(snapshot_dir / "config.json", "w") as f:
        json.dump(config_data, f, indent=2)

    # 2. Current positions
    with get_db_session() as db:
        positions = db.query(Position).filter_by(status="OPEN").all()
        positions_data = [
            {
                "position_id": p.position_id,
                "symbol": p.symbol,
                "side": p.side.value if hasattr(p.side, 'value') else str(p.side),
                "qty": p.qty,
                "avg_price": float(p.avg_price) if p.avg_price else 0.0,
                "current_price": float(p.current_price) if p.current_price else 0.0,
                "risk_amount": float(p.risk_amount) if p.risk_amount else 0.0,
                "oco_group": p.oco_group
            }
            for p in positions
        ]
        with open(snapshot_dir / "positions.json", "w") as f:
            json.dump(positions_data, f, indent=2)

        # 3. Top 100 audit logs
        audit_logs = db.query(AuditLog).order_by(AuditLog.ts.desc()).limit(100).all()
        logs_data = [
            {
                "ts": log.ts.isoformat() if log.ts else None,
                "action": log.action.value if hasattr(log.action, 'value') else str(log.action),
                "details": log.details if isinstance(log.details, dict) else {}
            }
            for log in audit_logs
        ]
        with open(snapshot_dir / "audit_logs.json", "w") as f:
            json.dump(logs_data, f, indent=2)

        # 4. Recent risk events
        risk_events = db.query(RiskEvent).order_by(RiskEvent.ts.desc()).limit(50).all()
        events_data = [
            {
                "ts": event.ts.isoformat() if event.ts else None,
                "event_type": event.event_type,
                "severity": event.severity,
                "message": event.message,
                "details": event.details if isinstance(event.details, dict) else {}
            }
            for event in risk_events
        ]
        with open(snapshot_dir / "risk_events.json", "w") as f:
            json.dump(events_data, f, indent=2)

    # 5. Incident details
    incident_data = {
        "incident_type": incident_type,
        "timestamp": datetime.now().isoformat(),
        "details": details,
        "config_sha": config_data["config_sha"],
        "positions_count": len(positions_data),
        "git_sha": _get_git_sha()
    }
    with open(snapshot_dir / "incident.json", "w") as f:
        json.dump(incident_data, f, indent=2)

    logger.info("Incident snapshot created", snapshot_dir=str(snapshot_dir))

    return str(snapshot_dir)


def _get_git_sha() -> str:
    """Get current git SHA"""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"

