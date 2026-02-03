"""FastAPI main application"""
import asyncio
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from kiteconnect import KiteConnect
from prometheus_client import make_asgi_app
from pydantic import BaseModel, field_validator

from apps.api.auth import APIKeyMiddleware
from packages.core import compliance
from packages.core.config import app_config, settings
from packages.core.execution import ExecutionEngine
from packages.core.exits import ExitManager
from packages.core.instruments import InstrumentManager
from packages.core.kite_client import KiteClient
from packages.core.market_data import MarketDataStream
from packages.core.metrics import (
    get_metrics,
    is_leader,
    marketdata_heartbeat_seconds,
    metrics_app,
    order_stream_heartbeat_seconds,
    prelive_day2_age,
    prelive_day2_pass,
    scan_heartbeat_seconds,
)
from packages.core.models import Position, PositionStatus
from packages.core.oco import OCOManager
from packages.core.orchestrator import TradingOrchestrator
from packages.core.order_watcher import OrderWatcher
from packages.core.ranker import SignalRanker
from packages.core.redis_bus import RedisBus
from packages.core.risk import RiskManager
from packages.core.strategies import (
    OptionsRankerStrategy,
    ORBStrategy,
    Strategy,
    TrendPullbackStrategy,
)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger(__name__)

# Global state
class AppState:
    """Application state"""
    kite: KiteConnect = None
    instrument_manager: InstrumentManager = None
    market_data_stream: MarketDataStream = None
    risk_manager: RiskManager = None
    exit_manager: ExitManager = None
    execution_engine: ExecutionEngine = None
    ranker: SignalRanker = None
    orchestrator: TradingOrchestrator = None

    # Strategies
    strategies: Dict = {}
    strategy_list: List[Strategy] = []

    # Positions
    positions: List[Position] = []

    # Control flags
    is_paused: bool = False
    is_market_open: bool = False

    # Performance metrics
    trades_today: int = 0
    wins_today: int = 0
    losses_today: int = 0
    realized_pnl_today: float = 0.0


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting AITRAPP", mode=settings.app_mode.value)

    # Clock skew check (fail if drift > 2s)
    import subprocess
    try:
        result = subprocess.run(
            ["bash", "scripts/check_ntp_drift.sh"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            logger.warning(f"Clock drift check failed: {result.stderr}")
            # Don't fail startup, but log warning
    except Exception as e:
        logger.warning(f"Could not check clock drift: {e}")

    # Initialize Kite Connect
    app_state.kite = KiteConnect(api_key=settings.kite_api_key)
    app_state.kite.set_access_token(settings.kite_access_token)

    # Initialize managers
    app_state.instrument_manager = InstrumentManager(
        app_state.kite,
        app_config.universe,
        settings
    )

    app_state.risk_manager = RiskManager(app_config.risk)
    app_state.exit_manager = ExitManager(app_config.exits)

    app_state.execution_engine = ExecutionEngine(
        app_state.kite,
        app_config.execution,
        settings
    )

    # Initialize market data stream
    app_state.market_data_stream = MarketDataStream(
        settings=settings,
        window_seconds=[1, 5]
    )

    # Sync instruments
    await app_state.instrument_manager.sync_instruments()
    await app_state.instrument_manager.sync_fo_ban_list()

    # Build universe
    universe_tokens = await app_state.instrument_manager.build_universe()
    logger.info(f"Universe: {len(universe_tokens)} instruments")

    # Initialize strategies
    strategy_list = []
    for strategy_config in app_config.get_enabled_strategies():
        strategy = None
        if strategy_config.name == "ORB":
            strategy = ORBStrategy(strategy_config.name, strategy_config.params)
            app_state.strategies["ORB"] = strategy
        elif strategy_config.name == "TrendPullback":
            strategy = TrendPullbackStrategy(strategy_config.name, strategy_config.params)
            app_state.strategies["TrendPullback"] = strategy
        elif strategy_config.name == "OptionsRanker":
            strategy = OptionsRankerStrategy(strategy_config.name, strategy_config.params)
            app_state.strategies["OptionsRanker"] = strategy

        if strategy:
            strategy_list.append(strategy)

    app_state.strategy_list = strategy_list
    logger.info(f"Loaded {len(strategy_list)} strategies")

    # Initialize ranker
    app_state.ranker = SignalRanker(app_config.ranking)

    # Initialize market data stream
    app_state.market_data_stream.initialize()

    # Initialize Redis bus
    redis_bus = RedisBus()
    await redis_bus.connect()
    logger.info("Redis bus connected")

    # Initialize Kite client wrapper (if needed)
    kite_client = KiteClient(app_state.kite)

    # Initialize OCO manager
    oco_manager = OCOManager(kite_client)
    logger.info("OCO manager initialized")

    # Initialize orchestrator with Redis and OCO
    app_state.orchestrator = TradingOrchestrator(
        kite=app_state.kite,
        strategies=strategy_list,
        instrument_manager=app_state.instrument_manager,
        market_data_stream=app_state.market_data_stream,
        risk_manager=app_state.risk_manager,
        execution_engine=app_state.execution_engine,
        exit_manager=app_state.exit_manager,
        ranker=app_state.ranker,
        redis_bus=redis_bus,
        oco_manager=oco_manager
    )

    # Initialize OrderWatcher
    order_watcher = OrderWatcher(
        kite_client=kite_client,
        orchestrator=app_state.orchestrator,
        oco_manager=oco_manager,
        redis_bus=redis_bus,
        metrics=None  # Can pass metrics if needed
    )

    # Start heartbeat updater
    from packages.core.heartbeats import run_heartbeat_updater
    hb_stop = asyncio.Event()
    hb_task = asyncio.create_task(run_heartbeat_updater(1.0, hb_stop))
    app_state.hb_stop = hb_stop
    app_state.hb_task = hb_task
    logger.info("Heartbeat updater started")

    # Start paper tick simulator if in PAPER mode and market data not connected
    if settings.app_mode.value == "PAPER" and not app_state.market_data_stream.is_connected:
        async def run_paper_tick_simulator():
            """Simulate market data ticks in PAPER mode"""
            from packages.core.heartbeats import touch_marketdata
            while not hb_stop.is_set():
                touch_marketdata()
                await asyncio.sleep(0.5)  # Simulate tick every 500ms

        paper_tick_task = asyncio.create_task(run_paper_tick_simulator())
        app_state.paper_tick_task = paper_tick_task
        logger.info("Paper tick simulator started")

    # Start pre-live metrics refresh task (every 30s)
    async def refresh_prelive_metrics_task():
        """Periodic task to refresh pre-live gate metrics"""
        import json
        import time
        from pathlib import Path

        DAY2_DIR = Path("reports/burnin")
        FRESH_SECS = 36 * 3600

        def _latest_day2_json():
            files = sorted(DAY2_DIR.glob("day2_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            return files[0] if files else None

        while not hb_stop.is_set():
            try:
                p = _latest_day2_json()
                if not p:
                    prelive_day2_pass.set(0)
                    prelive_day2_age.set(float("inf"))
                else:
                    age = time.time() - p.stat().st_mtime
                    prelive_day2_age.set(age)
                    try:
                        with p.open() as f:
                            data = json.load(f)
                        if (data.get("status") == "PASS" and
                            int(data.get("leader", 0)) == 1 and
                            age <= FRESH_SECS):
                            prelive_day2_pass.set(1)
                        else:
                            prelive_day2_pass.set(0)
                    except Exception:
                        prelive_day2_pass.set(0)
            except Exception as e:
                logger.warning(f"Error refreshing pre-live metrics: {e}")
            await asyncio.sleep(30)  # Refresh every 30s

    prelive_metrics_task = asyncio.create_task(refresh_prelive_metrics_task())
    app_state.prelive_metrics_task = prelive_metrics_task
    logger.info("Pre-live metrics refresh task started")

    # Start background tasks
    logger.info("Starting background tasks...")
    tasks = [
        asyncio.create_task(app_state.orchestrator.start()),
        asyncio.create_task(order_watcher.start())
    ]
    app_state.tasks = tasks

    logger.info("AITRAPP started successfully")

    yield

    # Graceful shutdown
    logger.info("Shutting down AITRAPP")

    # Stop heartbeat updater
    if hasattr(app_state, 'hb_stop') and app_state.hb_stop:
        app_state.hb_stop.set()
    if hasattr(app_state, 'hb_task') and app_state.hb_task:
        try:
            await app_state.hb_task
        except Exception as e:
            logger.warning(f"Error stopping heartbeat updater: {e}")

    # Stop pre-live metrics refresh task
    if hasattr(app_state, 'prelive_metrics_task') and app_state.prelive_metrics_task:
        try:
            app_state.prelive_metrics_task.cancel()
            await app_state.prelive_metrics_task
        except Exception as e:
            logger.warning(f"Error stopping pre-live metrics task: {e}")

    # Stop paper tick simulator
    if hasattr(app_state, 'paper_tick_task') and app_state.paper_tick_task:
        try:
            app_state.paper_tick_task.cancel()
            await app_state.paper_tick_task
        except Exception as e:
            logger.warning(f"Error stopping paper tick simulator: {e}")

    # Pause orchestrator
    if app_state.orchestrator:
        await app_state.orchestrator.pause()
        try:
            await app_state.orchestrator.flatten_all()
        except Exception as e:
            logger.error("Error during flatten", error=str(e))

    # Stop OrderWatcher
    if order_watcher:
        order_watcher.stop()

    # Cancel all tasks
    for task in tasks:
        task.cancel()

    # Wait for tasks to complete
    await asyncio.gather(*tasks, return_exceptions=True)

    # Disconnect Redis
    if redis_bus:
        await redis_bus.disconnect()

    # Stop market data stream
    if app_state.market_data_stream:
        app_state.market_data_stream.stop()

    logger.info("AITRAPP stopped")


# Create FastAPI app
app = FastAPI(
    title="AITRAPP API",
    description="Autonomous Intelligent Trading Application",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add API Key Authentication
app.add_middleware(APIKeyMiddleware, public_paths=[
    "/",
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/kite/callback"
])

# Mount Prometheus metrics
if settings.enable_metrics:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

# Include debug routers
from apps.api import debug, debug_supervisor

app.include_router(debug.router, tags=["debug"])
app.include_router(debug_supervisor.router, tags=["debug"])

# Include auth router
from apps.api.routes import kite_auth

app.include_router(kite_auth.router, tags=["auth"])


# ===== API Models =====

class ModeChangeRequest(BaseModel):
    mode: str  # PAPER or LIVE
    confirmation: str = ""
    override_reason: Optional[str] = None  # Required for manual override


class PositionResponse(BaseModel):
    position_id: str
    instrument: str
    side: str
    quantity: int
    entry_price: float
    current_price: float
    unrealized_pnl: float
    pnl_pct: float


class SystemStateResponse(BaseModel):
    timestamp: str
    mode: str
    is_paused: bool
    is_market_open: bool
    positions_count: int
    trades_today: int
    win_rate: float
    daily_pnl: float


# ===== Control Endpoints =====

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "mode": settings.app_mode.value,
        "is_paused": app_state.is_paused,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/ready")
async def ready():
    """Readiness endpoint - returns 200 only when leader lock is held and all heartbeats are fresh"""

    HEARTBEAT_MAX = float(os.getenv("HEARTBEAT_MAX", "5"))

    # Prometheus client stores values on samples()[0].value
    def get_value(gauge):
        """Get current value from Prometheus gauge"""
        samples = list(gauge._samples())
        if samples:
            return samples[0].value
        return 999.0  # Default to stale if no samples

    try:
        leader_val = get_value(is_leader)
        md_heartbeat = get_value(marketdata_heartbeat_seconds)
        order_heartbeat = get_value(order_stream_heartbeat_seconds)
        scan_heartbeat = get_value(scan_heartbeat_seconds)

        ok = (
            leader_val == 1
            and md_heartbeat < HEARTBEAT_MAX
            and order_heartbeat < HEARTBEAT_MAX
            and scan_heartbeat < HEARTBEAT_MAX
        )

        if not ok:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "not_ready",
                    "leader": leader_val,
                    "marketdata_heartbeat": md_heartbeat,
                    "order_stream_heartbeat": order_heartbeat,
                    "scan_heartbeat": scan_heartbeat,
                    "heartbeat_max": HEARTBEAT_MAX
                }
            )

        return {
            "status": "ready",
            "leader": leader_val,
            "marketdata_heartbeat": md_heartbeat,
            "order_stream_heartbeat": order_heartbeat,
            "scan_heartbeat": scan_heartbeat
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Readiness check error: {str(e)}")


@app.get("/compliance/status")
def compliance_status():
    """SEBI/NSE compliance status endpoint"""
    expected_ip = os.getenv("EXPECTED_EGRESS_IP", "")
    algo_id = os.getenv("EXCHANGE_ALGO_ID", "").strip()
    tops_cap = int(os.getenv("TOPS_CAP_PER_SEC", "8"))
    mode_profile = os.getenv("MODE_PROFILE", "PERSONAL").upper()
    wl = os.getenv("WHITELISTED_CLIENTS", "")
    # broker session created_at iso if you persist it, else env fallback:
    oauth_created_iso = os.getenv("KITE_TOKEN_CREATED_AT_ISO")
    # active client IDs: if you have multiple mapped, load from your config/session
    active_clients = [settings.kite_user_id] if settings.kite_user_id else []

    ip_ok, ip_msg, curr_ip = compliance.check_static_ip(expected_ip)
    oauth_ok, oauth_msg = compliance.check_oauth_fresh(oauth_created_iso, 24)
    tops_ok, tops_msg = compliance.tops_cap_ok(tops_cap)
    algo_ok, algo_msg = compliance.algo_id_present(algo_id)
    fam_ok, fam_msg = (True, "provider mode") if mode_profile != "PERSONAL" else compliance.check_family_only(active_clients, wl)

    return {
        "mode": os.getenv("APP_MODE", "PAPER"),
        "profile": mode_profile,
        "expected_ip": expected_ip,
        "current_ip": curr_ip,
        "static_ip_ok": ip_ok,
        "static_ip_msg": ip_msg,
        "oauth_ok": oauth_ok,
        "oauth_msg": oauth_msg,
        "tops_ok": tops_ok,
        "tops_msg": tops_msg,
        "tops_cap_per_sec": tops_cap,
        "algo_id_ok": algo_ok,
        "algo_msg": algo_msg,
        "exchange_algo_id": algo_id,
        "family_ok": fam_ok,
        "family_msg": fam_msg,
    }


@app.post("/mode")
async def change_mode(request: ModeChangeRequest):
    """
    Change application mode (PAPER <-> LIVE).
    
    LIVE mode requires explicit confirmation and validates Day-2 scorer JSON.
    For manual override, provide override_reason (logged to AuditLog).
    """
    if request.mode not in ["PAPER", "LIVE"]:
        raise HTTPException(status_code=400, detail="Invalid mode. Must be PAPER or LIVE.")

    if request.mode == "LIVE":
        if request.confirmation != "CONFIRM LIVE TRADING":
            raise HTTPException(
                status_code=403,
                detail="LIVE mode requires confirmation: 'CONFIRM LIVE TRADING'"
            )

        # Additional safety checks for LIVE mode
        if len(app_state.positions) > 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot switch to LIVE mode with open positions. Close all positions first."
            )

        # Gate on scorer JSON: require Day-2 PASS before LIVE switch
        # Mirrors the shell gate logic (mtime-based selection, freshness, completeness)
        import json
        import subprocess
        import time
        from datetime import datetime
        from pathlib import Path

        DAY2_DIR = Path("reports/burnin")
        FRESH_SECS = 36 * 3600  # 36 hours

        def _latest_day2_json() -> Path | None:
            """Select latest Day-2 JSON by mtime (not filename)"""
            files = sorted(DAY2_DIR.glob("day2_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            return files[0] if files else None

        def _validate_day2_json_or_403():
            """Validate Day-2 JSON with same logic as shell gate"""
            p = _latest_day2_json()
            if not p:
                raise HTTPException(status_code=403, detail="Day-2 JSON missing")

            age = time.time() - p.stat().st_mtime
            if age > FRESH_SECS:
                raise HTTPException(status_code=403, detail=f"Day-2 JSON stale (age={int(age/3600)}h, max 36h)")

            with p.open() as f:
                data = json.load(f)

            # Required fields
            req = ["status", "leader", "heartbeats", "leader_changes", "duplicates", "orphans", "flatten_ms"]
            if any(k not in data for k in req):
                raise HTTPException(status_code=403, detail="Day-2 JSON incomplete")

            # Validate heartbeats structure
            if "heartbeats" not in data or not isinstance(data["heartbeats"], dict):
                raise HTTPException(status_code=403, detail="Day-2 JSON: heartbeats missing or invalid")

            hb = data["heartbeats"]
            hb_keys = ["market", "orders", "scan"]
            if any(k not in hb for k in hb_keys):
                raise HTTPException(status_code=403, detail="Day-2 JSON: heartbeat keys missing")

            # Hard checks (fail closed)
            if data.get("status") != "PASS":
                raise HTTPException(status_code=403, detail=f"Day-2 JSON status={data.get('status')} (expected PASS)")

            if int(data.get("leader", 0)) != 1:
                raise HTTPException(status_code=403, detail=f"Day-2 JSON leader={data.get('leader')} (expected 1)")

            if any(float(hb.get(k, 999)) >= 5 for k in hb_keys):
                raise HTTPException(status_code=403, detail=f"Day-2 JSON: heartbeats >= 5s (market={hb.get('market')}, orders={hb.get('orders')}, scan={hb.get('scan')})")

            if int(data.get("leader_changes", 999)) > 2:
                raise HTTPException(status_code=403, detail=f"Day-2 JSON: leader_changes={data.get('leader_changes')} (>2)")

            if int(data.get("duplicates", 999)) != 0:
                raise HTTPException(status_code=403, detail=f"Day-2 JSON: duplicates={data.get('duplicates')} (!=0)")

            if int(data.get("orphans", 999)) != 0:
                raise HTTPException(status_code=403, detail=f"Day-2 JSON: orphans={data.get('orphans')} (!=0)")

            if float(data.get("flatten_ms", 9999)) > 2000:
                raise HTTPException(status_code=403, detail=f"Day-2 JSON: flatten_ms={data.get('flatten_ms')}ms (>2000ms)")

        # Find latest Day-2 JSON by mtime (not filename)
        day2_json = _latest_day2_json()

        if day2_json and day2_json.exists():
            try:
                # Use the same validation logic as shell gate
                _validate_day2_json_or_403()

                # Additional: Validate config_sha and git_head match runtime
                with open(day2_json) as f:
                    day2_data = json.load(f)

                runtime_config_sha = None
                runtime_git_head = None

                try:
                    import hashlib
                    with open("configs/app.yaml", "rb") as f:
                        runtime_config_sha = hashlib.sha256(f.read()).hexdigest()[:16]
                except Exception:
                    pass

                try:
                    result = subprocess.run(
                        ["git", "rev-parse", "--short", "HEAD"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        runtime_git_head = result.stdout.strip()
                except Exception:
                    pass

                json_config_sha = day2_data.get("config_sha")
                json_git_head = day2_data.get("git_head")

                if runtime_config_sha and json_config_sha and runtime_config_sha != json_config_sha:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Config SHA mismatch (JSON={json_config_sha}, runtime={runtime_config_sha}). Config changed after Day-2 PASS. Cannot switch to LIVE."
                    )

                if runtime_git_head and json_git_head and runtime_git_head != json_git_head:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Git HEAD mismatch (JSON={json_git_head}, runtime={runtime_git_head}). Code changed after Day-2 PASS. Cannot switch to LIVE."
                    )

                logger.info("Day-2 scorer JSON check passed with full validation", json_file=str(day2_json))
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Could not validate Day-2 scorer JSON: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error validating Day-2 scorer JSON: {str(e)}"
                )
        else:
            logger.warning("No Day-2 scorer JSON found - proceeding with caution")
            # Don't block, but warn

        # Mode safety: assert APP_MODE isn't already LIVE
        if settings.app_mode.value == "LIVE":
            raise HTTPException(
                status_code=400,
                detail="Already in LIVE mode. No need to switch again."
            )

        # Log config_sha + git_head to AuditLog before flip (hardens audit trail)
        try:
            import hashlib
            import subprocess

            from packages.storage.persistence import get_db_session

            from packages.storage.models import AuditActionEnum, AuditLog

            runtime_config_sha = None
            runtime_git_head = None

            try:
                with open("configs/app.yaml", "rb") as f:
                    runtime_config_sha = hashlib.sha256(f.read()).hexdigest()[:16]
            except Exception:
                pass

            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    runtime_git_head = result.stdout.strip()
            except Exception:
                pass

            async with get_db_session() as session:
                audit_log = AuditLog(
                    action=AuditActionEnum.MODE_CHANGE,
                    details={
                        "mode": "LIVE",
                        "config_sha": runtime_config_sha or "unknown",
                        "git_head": runtime_git_head or "unknown",
                        "timestamp": datetime.now().isoformat(),
                        "day2_json_validated": day2_json is not None
                    }
                )
                session.add(audit_log)
                await session.commit()
                logger.info("Mode change logged to AuditLog", config_sha=runtime_config_sha, git_head=runtime_git_head)
        except Exception as e:
            logger.warning(f"Could not log mode change to AuditLog: {e}")
            # Don't block mode change if audit logging fails

        # Manual override check
        override_reason = getattr(request, "override_reason", None)
        if override_reason:
            # Log override to AuditLog
            from packages.storage.persistence import get_db_session

            from packages.storage.models import AuditActionEnum, AuditLog
            try:
                async with get_db_session() as session:
                    audit_log = AuditLog(
                        action=AuditActionEnum.MODE_CHANGE,
                        details={
                            "mode": "LIVE",
                            "override": True,
                            "override_reason": override_reason,
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                    session.add(audit_log)
                    await session.commit()
            except Exception as e:
                logger.warning(f"Could not log override to AuditLog: {e}")

            # Create incident snapshot before flipping
            try:
                import subprocess
                snapshot_dir = Path("reports/incidents")
                snapshot_dir.mkdir(parents=True, exist_ok=True)
                snapshot_file = snapshot_dir / f"override_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(snapshot_file, "w") as f:
                    f.write("LIVE Mode Override Snapshot\n")
                    f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                    f.write(f"Override Reason: {override_reason}\n")
                    f.write(f"Git HEAD: {subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()}\n")
                    f.write(f"Config SHA: {runtime_config_sha if 'runtime_config_sha' in locals() else 'unknown'}\n")
                    f.write(f"Positions: {len(app_state.positions)}\n")
                    f.write(f"Paused: {app_state.is_paused}\n")
                logger.warning(f"Incident snapshot created: {snapshot_file}")
            except Exception as e:
                logger.warning(f"Could not create incident snapshot: {e}")

        logger.warning("⚠️  SWITCHING TO LIVE MODE ⚠️")

    # Update mode
    settings.app_mode = request.mode
    app_config.mode = request.mode

    logger.info(f"Mode changed to {request.mode}")

    return {
        "status": "success",
        "mode": request.mode,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/pause")
async def pause_trading():
    """
    PAUSE trading: Stop new signals and cancel pending orders.
    Does NOT close existing positions (use /flatten for that).
    """
    if app_state.orchestrator:
        await app_state.orchestrator.pause()
        app_state.is_paused = True

    logger.warning("🛑 TRADING PAUSED")

    return {
        "status": "paused",
        "timestamp": datetime.now().isoformat(),
        "message": "Trading paused. No new positions will be opened."
    }


@app.post("/resume")
async def resume_trading():
    """Resume trading after pause"""
    if app_state.orchestrator:
        await app_state.orchestrator.resume()
        app_state.is_paused = False

    logger.info("▶️  TRADING RESUMED")

    return {
        "status": "resumed",
        "timestamp": datetime.now().isoformat()
    }


@app.post("/flatten")
async def flatten_all(reason: str = "manual"):
    """
    KILL SWITCH: Close all positions immediately with market orders.
    Also pauses trading.
    
    Args:
        reason: Reason for kill switch (manual|eod|risk)
    """
    try:
        if app_state.orchestrator:
            await app_state.orchestrator.flatten_all(reason=reason)
            app_state.is_paused = True

        logger.critical("🚨 KILL SWITCH ACTIVATED - FLATTENING ALL POSITIONS", reason=reason)

        return {
            "status": "flattened",
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "message": "All positions closed. Trading paused."
        }
    except Exception as e:
        logger.error(f"Error in flatten: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Flatten failed: {str(e)}")


# ===== Data Endpoints =====

@app.get("/positions")
async def get_positions():
    """Get all open positions"""
    positions_list = app_state.orchestrator.positions if app_state.orchestrator else app_state.positions

    positions = [
        PositionResponse(
            position_id=pos.position_id,
            instrument=pos.instrument.tradingsymbol if pos.instrument else "UNKNOWN",
            side=pos.side.value,
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            current_price=pos.current_price,
            unrealized_pnl=pos.unrealized_pnl,
            pnl_pct=pos.pnl_pct
        )
        for pos in positions_list if pos.is_open
    ]

    return {
        "positions": positions,
        "count": len(positions)
    }


@app.post("/positions/{position_id}/close")
async def close_position(position_id: str):
    """Close a specific position"""
    position = next((p for p in app_state.positions if p.position_id == position_id), None)

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    if not position.is_open:
        raise HTTPException(status_code=400, detail="Position already closed")

    try:
        order = await app_state.execution_engine.close_position(
            position,
            reason="MANUAL_CLOSE"
        )

        if order:
            position.status = PositionStatus.CLOSED

            return {
                "status": "success",
                "position_id": position_id,
                "order_id": order.order_id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to place close order")

    except Exception as e:
        logger.error(f"Error closing position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/state")
async def get_system_state():
    """Get current system state"""
    try:
        if app_state.orchestrator:
            system_state = app_state.orchestrator.get_system_state()
            return SystemStateResponse(
                timestamp=system_state.timestamp.isoformat(),
                mode=system_state.mode,
                is_paused=system_state.is_paused,
                is_market_open=system_state.is_market_open,
                positions_count=system_state.portfolio.total_positions,
                trades_today=system_state.trades_today,
                win_rate=system_state.win_rate,
                daily_pnl=system_state.portfolio.daily_pnl
            )
        else:
            # Fallback if orchestrator not initialized
            win_rate = 0.0
            if app_state.trades_today > 0:
                win_rate = (app_state.wins_today / app_state.trades_today) * 100

            return SystemStateResponse(
                timestamp=datetime.now().isoformat(),
                mode=settings.app_mode.value,
                is_paused=app_state.is_paused,
                is_market_open=app_state.is_market_open,
                positions_count=len([p for p in app_state.positions if p.is_open]),
                trades_today=app_state.trades_today,
                win_rate=win_rate,
                daily_pnl=app_state.realized_pnl_today
            )
    except Exception as e:
        logger.error(f"Error getting system state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/orders")
async def get_orders():
    """Get all orders"""
    orders = app_state.execution_engine.orders.values()

    return {
        "orders": [
            {
                "order_id": order.order_id,
                "client_order_id": order.client_order_id,
                "timestamp": order.timestamp.isoformat(),
                "side": order.side,
                "quantity": order.quantity,
                "price": order.price,
                "status": order.status.value,
                "filled_quantity": order.filled_quantity
            }
            for order in orders
        ],
        "count": len(orders)
    }


@app.post("/universe/reload")
async def reload_universe():
    """Reload trading universe"""
    try:
        await app_state.instrument_manager.sync_instruments()
        await app_state.instrument_manager.sync_fo_ban_list()
        universe_tokens = await app_state.instrument_manager.build_universe()

        return {
            "status": "success",
            "universe_size": len(universe_tokens),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to reload universe: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/strategies/reload")
async def reload_strategies():
    """Reload strategy configurations"""
    try:
        app_config.reload()

        # Reinitialize strategies
        app_state.strategies.clear()

        for strategy_config in app_config.get_enabled_strategies():
            if strategy_config.name == "ORB":
                app_state.strategies["ORB"] = ORBStrategy(
                    strategy_config.name,
                    strategy_config.params
                )
            elif strategy_config.name == "TrendPullback":
                app_state.strategies["TrendPullback"] = TrendPullbackStrategy(
                    strategy_config.name,
                    strategy_config.params
                )
            elif strategy_config.name == "OptionsRanker":
                app_state.strategies["OptionsRanker"] = OptionsRankerStrategy(
                    strategy_config.name,
                    strategy_config.params
                )

        return {
            "status": "success",
            "strategies_loaded": len(app_state.strategies),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to reload strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BacktestRequest(BaseModel):
    """Backtest request model"""
    symbol: str = "NIFTY"  # NIFTY or BANKNIFTY
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    initial_capital: float = 1000000
    strategy: str = "all"  # ORB, TrendPullback, OptionsRanker, or all

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError('Symbol must be alphanumeric')
        return v


@app.post("/backtest")
async def run_backtest(request: BacktestRequest):
    """
    Run backtest on historical data.
    
    This endpoint runs strategies on historical NSE options data
    and returns performance metrics.
    """
    try:
        from packages.core.backtest import BacktestEngine

        # Parse dates
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")

        # Initialize strategies
        strategies = []

        if request.strategy == "all" or request.strategy == "ORB":
            orb_config = app_config.get_strategy_by_name("ORB")
            if orb_config:
                strategies.append(ORBStrategy("ORB", orb_config.params))

        if request.strategy == "all" or request.strategy == "TrendPullback":
            tp_config = app_config.get_strategy_by_name("TrendPullback")
            if tp_config:
                strategies.append(TrendPullbackStrategy("TrendPullback", tp_config.params))

        if request.strategy == "all" or request.strategy == "OptionsRanker":
            opt_config = app_config.get_strategy_by_name("OptionsRanker")
            if opt_config:
                strategies.append(OptionsRankerStrategy("OptionsRanker", opt_config.params))

        if not strategies:
            raise HTTPException(
                status_code=400,
                detail="No strategies configured. Check configs/app.yaml"
            )

        # Run backtest
        engine = BacktestEngine(
            initial_capital=request.initial_capital,
            data_dir="docs/NSE OPINONS DATA"
        )

        results = engine.run_backtest(
            strategies=strategies,
            symbol=request.symbol,
            start_date=start_date,
            end_date=end_date
        )

        return {
            "status": "success",
            "results": results,
            "trades": engine.closed_trades[:100],  # First 100 trades
            "timestamp": datetime.now().isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Historical data not found: {e}")
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=get_metrics(), media_type="text/plain")


@app.get("/risk")
async def get_risk_state():
    """Get current risk state"""
    try:
        if not app_state.orchestrator or not app_state.risk_manager:
            raise HTTPException(status_code=503, detail="Risk manager not initialized")

        # Get portfolio risk
        portfolio_risk = app_state.orchestrator._get_portfolio_risk()

        return {
            "net_liquid": portfolio_risk.net_liquid,
            "used_margin": portfolio_risk.used_margin,
            "available_margin": portfolio_risk.available_margin,
            "total_risk_amount": portfolio_risk.total_risk_amount,
            "portfolio_heat_pct": portfolio_risk.portfolio_heat_pct,
            "unrealized_pnl": portfolio_risk.unrealized_pnl,
            "realized_pnl_today": portfolio_risk.realized_pnl_today,
            "daily_pnl": portfolio_risk.daily_pnl,
            "daily_pnl_pct": portfolio_risk.daily_pnl_pct,
            "daily_loss_limit": portfolio_risk.daily_loss_limit,
            "max_portfolio_heat": portfolio_risk.max_portfolio_heat,
            "is_daily_loss_breached": portfolio_risk.is_daily_loss_breached,
            "is_heat_limit_breached": portfolio_risk.is_heat_limit_breached,
            "can_take_new_position": portfolio_risk.can_take_new_position,
            "open_positions_count": len(portfolio_risk.open_positions),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting risk state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "AITRAPP API",
        "version": "1.0.0",
        "mode": settings.app_mode.value,
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "apps.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.reload,
        log_level=settings.log_level.lower()
    )
