"""Config immutability guard for LIVE mode"""
from datetime import datetime
from typing import Optional

import structlog

from packages.core.config import app_config, settings
from packages.storage.database import get_db_session
from packages.storage.models import AuditActionEnum, AuditLog

logger = structlog.get_logger(__name__)


class ConfigGuard:
    """Prevents runtime config changes in LIVE mode"""

    def __init__(self):
        self.frozen_config_sha: Optional[str] = None
        self.frozen_at: Optional[str] = None

    def freeze_config(self) -> str:
        """
        Freeze current config SHA (call on LIVE mode switch).

        Returns:
            Config SHA that was frozen
        """
        config_sha = getattr(app_config, 'config_sha', 'unknown')
        self.frozen_config_sha = config_sha
        self.frozen_at = datetime.now().isoformat()

        logger.info("Config frozen", config_sha=config_sha, frozen_at=self.frozen_at)

        # Audit log
        with get_db_session() as db:
            from sqlalchemy import inspect

            # Check if details column exists
            try:
                columns = inspect(db.bind).get_columns("audit_logs")
                has_details = any(
                    c.get("name") == "details" or getattr(c, "name", None) == "details"
                    for c in columns
                )
            except Exception:
                # Fallback: assume details exists if we can't check
                has_details = True

            action_value = AuditActionEnum.CONFIG_FROZEN
            # AuditActionEnum values are already strings, so use directly
            if isinstance(action_value, str):
                pass  # Already a string
            elif hasattr(action_value, 'value'):
                action_value = action_value.value
            else:
                action_value = str(action_value)

            if has_details:
                audit_log = AuditLog(
                    action=action_value,
                    message="Config frozen for LIVE mode",
                    details={
                        "config_sha": config_sha,
                        "frozen_at": self.frozen_at
                    }
                )
            else:
                audit_log = AuditLog(
                    action=str(action_value),
                    message="Config frozen for LIVE mode",
                    data={
                        "config_sha": config_sha,
                        "frozen_at": self.frozen_at
                    }
                )
            db.add(audit_log)
            db.commit()

        return config_sha

    def check_config_change(self) -> bool:
        """
        Check if config has changed since freeze.

        Returns:
            True if config changed (requires restart)
        """
        if not self.frozen_config_sha:
            return False  # Not frozen yet

        current_sha = getattr(app_config, 'config_sha', 'unknown')

        if current_sha != self.frozen_config_sha:
            logger.warning(
                "Config changed since freeze",
                frozen_sha=self.frozen_config_sha,
                current_sha=current_sha
            )
            return True

        return False

    def reject_runtime_change(self, change_type: str, details: dict) -> None:
        """
        Reject a runtime config change in LIVE mode.

        Args:
            change_type: Type of change attempted
            details: Details of the change
        """
        if settings.app_mode.value != "LIVE":
            return  # Only enforce in LIVE mode

        logger.critical(
            "Runtime config change rejected in LIVE mode",
            change_type=change_type,
            details=details,
            frozen_sha=self.frozen_config_sha
        )

        # Audit log (no specific action enum for this, use message only)
        with get_db_session() as db:
            audit_log = AuditLog(
                message=f"Runtime config change rejected: {change_type}",
                level="CRITICAL",
                category="ORCH",
                details={
                    "change_type": change_type,
                    "details": details,
                    "frozen_sha": self.frozen_config_sha
                }
            )
            db.add(audit_log)
            db.commit()

        raise RuntimeError(
            f"Runtime config changes not allowed in LIVE mode. "
            f"Config was frozen at {self.frozen_at} with SHA {self.frozen_config_sha}. "
            f"Restart required to apply changes."
        )

    def unfreeze(self) -> None:
        """Unfreeze config (call on switch back to PAPER)"""
        self.frozen_config_sha = None
        self.frozen_at = None
        logger.info("Config unfrozen")
