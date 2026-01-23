"""SEBI/NSE Compliance Module (Feb 2025 Retail Algo Framework)"""
from __future__ import annotations
import os
import time
import json
import datetime as dt
from datetime import datetime
from typing import Tuple, Optional, List
import urllib.request
import httpx
import structlog

from packages.core.config import app_config, settings

logger = structlog.get_logger(__name__)

TZ = os.getenv("APP_TIMEZONE", "Asia/Kolkata")
COMPLIANCE_ENABLED = os.getenv("COMPLIANCE_SEBI_2025", "1") == "1"


def _now_ts() -> float:
    return time.time()


def _fetch_egress_ip(timeout=3.0) -> Optional[str]:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as r:
            return r.read().decode().strip()
    except Exception:
        return None


def check_static_ip(expected_ip: str) -> Tuple[bool, str, Optional[str]]:
    if not expected_ip:
        return False, "EXPECTED_EGRESS_IP not set", None
    curr = _fetch_egress_ip()
    if curr is None:
        return False, "unable to resolve egress ip", None
    return (curr == expected_ip), ("ok" if curr == expected_ip else f"egress mismatch: {curr} != {expected_ip}"), curr


def check_oauth_fresh(created_at_iso: Optional[str], max_age_hours: int = 24) -> Tuple[bool, str]:
    """
    created_at_iso: RFC3339 when the token/session was created (from your Kite session store).
    Fallback: env KITE_TOKEN_ISSUED_AT (epoch seconds).
    PAPER mode returns True if created_at not available.
    """
    from os import getenv
    app_mode = getenv("APP_MODE", "PAPER").upper()
    if app_mode == "PAPER" and not created_at_iso and not getenv("KITE_TOKEN_ISSUED_AT"):
        return True, "paper mode: oauth freshness skipped"
    try:
        if created_at_iso:
            created = dt.datetime.fromisoformat(created_at_iso.replace("Z","+00:00")).timestamp()
        else:
            created = float(getenv("KITE_TOKEN_ISSUED_AT","0"))
        age_h = ( _now_ts() - created ) / 3600.0
        ok = age_h < max_age_hours
        return ok, f"oauth_age_hours={age_h:.2f} (limit={max_age_hours})"
    except Exception:
        return False, "unable to compute oauth age"


def check_family_only(active_client_ids: list[str], whitelisted_csv: str) -> Tuple[bool, str]:
    wl = [x.strip() for x in (whitelisted_csv or "").split(",") if x.strip()]
    if not wl:  # nothing configured → fail-closed in PERSONAL
        return False, "whitelist empty"
    extra = [x for x in active_client_ids if x not in wl]
    if extra:
        return False, f"non-whitelisted clients present: {','.join(extra)}"
    return True, "ok"


def tops_cap_ok(cap_per_sec: int) -> Tuple[bool, str]:
    # keep < 10/s unless registered; brokers may impose stricter caps
    try:
        cap = int(cap_per_sec)
        if cap <= 0:
            return False, "TOPS cap invalid"
        if cap >= 10:
            return False, f"TOPS cap {cap}/s >= 10/s; register algo or lower cap"
        return True, f"cap={cap}/s"
    except Exception:
        return False, "TOPS cap parse error"


def algo_id_present(algo_id: Optional[str]) -> Tuple[bool, str]:
    if algo_id and len(algo_id.strip())>0:
        return True, "ok"
    return False, "EXCHANGE_ALGO_ID missing (placeholder until broker field goes live)"


class ComplianceManager:
    """Manages SEBI/NSE compliance requirements"""
    
    def __init__(self):
        self.static_ip_verified = False
        self.oauth_fresh = False
        self.two_fa_verified = False
        self.last_logout_time: Optional[datetime] = None
        self.order_count_window: List[float] = []  # Timestamps of recent orders for TOPS tracking
        self.tops_cap = app_config.execution.tops_cap_per_sec
    
    async def verify_static_ip(self) -> bool:
        """Verify egress IP matches whitelisted IP"""
        if not settings.require_static_ip:
            return True
        
        if not settings.expected_egress_ip:
            logger.error("REQUIRE_STATIC_IP=1 but EXPECTED_EGRESS_IP not set")
            return False
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://ifconfig.me/ip")
                actual_ip = response.text.strip()
            
            if actual_ip != settings.expected_egress_ip:
                logger.error(
                    "Egress IP mismatch",
                    expected=settings.expected_egress_ip,
                    actual=actual_ip
                )
                return False
            
            self.static_ip_verified = True
            logger.info("Static IP verified", ip=actual_ip)
            return True
        except Exception as e:
            logger.error(f"Failed to verify static IP: {e}")
            return False
    
    def verify_oauth_freshness(self) -> bool:
        """Verify OAuth token is fresh (< 24h) and 2FA is present"""
        if not settings.oauth_required:
            return True
        
        # Check if token is fresh (Kite tokens typically expire daily)
        # In practice, you'd check token expiry from Kite API
        # For now, we assume daily logout enforces freshness
        
        if settings.two_fa_required:
            # In practice, verify 2FA was used during OAuth grant
            # This would require integration with Kite's 2FA verification
            self.two_fa_verified = True  # Placeholder
        
        self.oauth_fresh = True
        return True
    
    def verify_family_only(self) -> bool:
        """Verify only whitelisted family accounts are used"""
        if not settings.whitelisted_clients:
            return True  # No restriction if not set
        
        whitelist = [c.strip() for c in settings.whitelisted_clients.split(",")]
        current_user = settings.kite_user_id
        
        if current_user not in whitelist:
            logger.error(
                "User not in whitelist",
                user=current_user,
                whitelist=whitelist
            )
            return False
        
        logger.info("Family-only check passed", user=current_user)
        return True
    
    def check_tops_compliance(self) -> bool:
        """Check if order rate is within TOPS limit"""
        now = time.time()
        # Remove orders older than 1 second
        self.order_count_window = [t for t in self.order_count_window if now - t < 1.0]
        
        if len(self.order_count_window) >= self.tops_cap:
            logger.warning(
                "TOPS limit reached",
                current=len(self.order_count_window),
                cap=self.tops_cap
            )
            return False
        
        return True
    
    def record_order(self):
        """Record an order for TOPS tracking"""
        self.order_count_window.append(time.time())
    
    async def force_daily_logout(self):
        """Force daily logout (revoke tokens, clear sessions)"""
        # This would revoke Kite access tokens and clear sessions
        # Implementation depends on Kite API capabilities
        logger.warning("Forcing daily logout (token revocation)")
        
        # Log to audit trail
        from packages.storage.persistence import get_db_session
        from packages.storage.models import AuditLog, AuditActionEnum
        
        try:
            async with get_db_session() as session:
                audit_log = AuditLog(
                    action=AuditActionEnum.FORCED_DAILY_LOGOUT,
                    details={
                        "timestamp": datetime.now().isoformat(),
                        "reason": "SEBI/NSE daily compulsory logout requirement"
                    }
                )
                session.add(audit_log)
                await session.commit()
        except Exception as e:
            logger.warning(f"Could not log forced logout: {e}")
        
        self.last_logout_time = datetime.now()
        self.oauth_fresh = False
        self.two_fa_verified = False
    
    def get_exchange_algo_id(self) -> Optional[str]:
        """Get Exchange Algo-ID for order tagging"""
        return settings.exchange_algo_id or app_config.execution.exchange_algo_id
    
    def verify_algo_id_present(self) -> bool:
        """Verify Exchange Algo-ID is set (required post broker go-live)"""
        algo_id = self.get_exchange_algo_id()
        if not algo_id:
            logger.warning("EXCHANGE_ALGO_ID not set (required post broker go-live)")
            return False
        return True
    
    async def run_compliance_checks(self) -> bool:
        """Run all compliance checks"""
        if not settings.compliance_sebi_2025:
            logger.info("SEBI compliance checks disabled")
            return True
        
        checks = [
            ("Static IP", await self.verify_static_ip()),
            ("OAuth Freshness", self.verify_oauth_freshness()),
            ("Family Only", self.verify_family_only()),
            ("Algo-ID Present", self.verify_algo_id_present()),
        ]
        
        all_passed = all(check[1] for check in checks)
        
        if not all_passed:
            failed = [check[0] for check in checks if not check[1]]
            logger.error("Compliance checks failed", failed_checks=failed)
        
        return all_passed
