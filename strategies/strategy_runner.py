#!/usr/bin/env python3
"""
OpenAlgo Production Strategy Runner
===================================
Executes trades based on production_strategy_config.py
Target: ₹50,000/day | Max Loss: ₹10,000/day

Usage:
    python strategy_runner.py --segment=EQUITY --action=start
    python strategy_runner.py --segment=FNO_OPTIONS --action=start
    python strategy_runner.py --segment=MCX --action=start
    python strategy_runner.py --action=status
"""

import os
import sys
import json
import argparse
import logging
import time as time_module
from datetime import datetime
from pathlib import Path
import math
from urllib import error as urllib_error
from urllib import request as urllib_request

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# Add parent directory to path
current_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(current_dir))

# Add openalgo root to path for util imports
root_dir = current_dir.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "openalgo"))

# Load environment variables
try:
    from dotenv import load_dotenv

    # Always prefer repository .env values over inherited parent-process env.
    load_dotenv(root_dir / ".env", override=True)
except ImportError:
    print(
        "Warning: python-dotenv not installed. Environment variables might be missing."
    )

from production_strategy_config import (
    RISK_CONFIG,
    SEGMENT_CONFIGS,
    STRATEGY_PARAMS,
    SESSION_CONFIG,
)

# Import Trading Utils
try:
    from strategies.utils.trading_utils import APIClient, is_market_open
except ImportError:
    try:
        from openalgo.strategies.utils.trading_utils import APIClient, is_market_open
    except ImportError:
        print("Warning: Could not import trading_utils. Running in simulation mode.")
        APIClient = None
        is_market_open = lambda x="NSE": True

try:
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    try:
        from strategies.utils.symbol_resolver import SymbolResolver
    except ImportError:
        SymbolResolver = None

try:
    from broker.dhan.api.data import BrokerData
except Exception:
    BrokerData = None

try:
    from openalgo.agent import get_agent_client
    from openalgo.agent.schemas import DecisionRequest
except Exception:
    try:
        from agent import get_agent_client
        from agent.schemas import DecisionRequest
    except Exception:
        get_agent_client = None
        DecisionRequest = None

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


class TradingSession:
    def __init__(self, segment="EQUITY"):
        self.segment = segment
        self.segment_config = SEGMENT_CONFIGS.get(segment, {})
        self.daily_pnl = 0
        self.positions = []
        self.trades_today = 0
        self.start_time = datetime.now()
        self.last_prices = {}
        self.last_symbol_prices = {}
        self.resolved_symbols = {}
        self.blind_entry_attempted = set()
        self.last_blind_add_loop = {}
        self.peak_pnl = 0.0
        self.trailing_lock_triggered = False
        self.trailing_lock_reason = ""
        self._lock_warned = False
        self.symbol_resolver = SymbolResolver() if SymbolResolver else None
        self.dhan_data = None
        self._dhan_fallback_logged = set()
        self.direct_quotes_only = _env_bool("OA_DIRECT_DHAN_QUOTES_ONLY", False)
        self._openalgo_quote_failures = 0
        self._openalgo_quote_skip_until = 0.0
        self.pretrade_mtm_gate = _env_bool("OA_PRETRADE_MTM_GATE", True)
        try:
            self.pretrade_mtm_refresh_sec = max(
                0.5, float(os.getenv("OA_PRETRADE_MTM_REFRESH_SEC", "3"))
            )
        except Exception:
            self.pretrade_mtm_refresh_sec = 3.0
        self._last_pretrade_mtm_refresh_ts = 0.0
        self.require_auth_session = _env_bool("OA_REQUIRE_AUTH_SESSION", True)
        self.auth_status_url = os.getenv(
            "OA_AUTH_STATUS_URL", "http://127.0.0.1:5002/auth/session-status"
        ).strip()
        try:
            self.auth_status_refresh_sec = max(
                0.5, float(os.getenv("OA_AUTH_STATUS_REFRESH_SEC", "5"))
            )
        except Exception:
            self.auth_status_refresh_sec = 5.0
        try:
            self.auth_status_timeout_sec = max(
                0.5, float(os.getenv("OA_AUTH_STATUS_TIMEOUT_SEC", "2"))
            )
        except Exception:
            self.auth_status_timeout_sec = 2.0
        self.auth_status_fail_open = _env_bool("OA_AUTH_STATUS_FAIL_OPEN", False)
        self._last_auth_status_check_ts = 0.0
        self._cached_auth_ok = True
        self._auth_warned = False
        self.enforce_daily_lock = _env_bool("OA_ENFORCE_DAILY_LOCK", True)
        lock_default = root_dir / "openalgo" / "logs" / "runner_risk_lock_state.json"
        self.lock_file = Path(os.getenv("OA_RISK_LOCK_FILE", str(lock_default))).expanduser()

        # Initialize API Client
        if APIClient:
            self.client = APIClient(
                api_key=SESSION_CONFIG.get("api_key"),
                host=SESSION_CONFIG.get("api_host"),
            )
        else:
            self.client = None

        # Optional direct-Dhan quote fallback if OpenAlgo quote API hangs.
        if _env_bool("OA_FALLBACK_DHAN_QUOTES", True) and BrokerData:
            token = (os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
            if token:
                try:
                    self.dhan_data = BrokerData(token)
                except Exception as e:
                    logger.warning(f"Dhan direct quote fallback unavailable: {e}")

        if self.enforce_daily_lock:
            self.restore_persistent_daily_lock()

    def _ist_now(self):
        if ZoneInfo:
            try:
                return datetime.now(ZoneInfo("Asia/Kolkata"))
            except Exception:
                pass
        return datetime.now()

    def _trading_day_key(self):
        return self._ist_now().strftime("%Y-%m-%d")

    def _read_lock_state(self):
        if not self.lock_file.exists():
            return {}
        try:
            payload = json.loads(self.lock_file.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _write_lock_state(self, state):
        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.lock_file.with_suffix(self.lock_file.suffix + ".tmp")
            tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
            tmp.replace(self.lock_file)
        except Exception as e:
            logger.warning(f"Could not persist risk lock state: {e}")

    def restore_persistent_daily_lock(self):
        state = self._read_lock_state()
        if not state:
            return

        today = self._trading_day_key()
        stale_keys = []
        for seg, rec in state.items():
            if not isinstance(rec, dict):
                stale_keys.append(seg)
                continue
            if rec.get("date") != today:
                stale_keys.append(seg)
        for seg in stale_keys:
            state.pop(seg, None)
        if stale_keys:
            self._write_lock_state(state)

        rec = state.get(self.segment)
        if not isinstance(rec, dict) or not rec.get("locked"):
            return

        reason = str(rec.get("reason") or "Persistent daily lock active")
        pnl = rec.get("pnl")
        if pnl is not None:
            try:
                self.daily_pnl = float(pnl)
            except Exception:
                pass
        self.trailing_lock_triggered = True
        self.trailing_lock_reason = f"{reason} [day={today}]"
        logger.error(f"🔒 DAILY LOCK RESTORED ({self.segment}): {self.trailing_lock_reason}")

    def persist_daily_lock(self, reason):
        if not self.enforce_daily_lock:
            return

        today = self._trading_day_key()
        state = self._read_lock_state()
        if not isinstance(state, dict):
            state = {}
        state[self.segment] = {
            "locked": True,
            "date": today,
            "reason": str(reason),
            "pnl": float(self.daily_pnl),
            "updated_at": self._ist_now().isoformat(),
        }
        self._write_lock_state(state)
        self.trailing_lock_triggered = True
        self.trailing_lock_reason = str(reason)

    def refresh_pnl_for_pretrade_gate(self, force=False):
        """
        Update daily_pnl from broker/Dhan MTM before evaluating risk checks.
        This prevents stale in-memory PnL from allowing extra entries.
        """
        if not self.pretrade_mtm_gate:
            return
        if self.segment not in ("FNO_OPTIONS", "MCX"):
            return

        now_ts = time_module.time()
        if (
            (not force)
            and self._last_pretrade_mtm_refresh_ts
            and (now_ts - self._last_pretrade_mtm_refresh_ts) < self.pretrade_mtm_refresh_sec
        ):
            return
        self._last_pretrade_mtm_refresh_ts = now_ts
        self.update_pnl_from_broker_positions()

    def refresh_auth_status(self, force=False):
        """
        Cache local auth session status to avoid avoidable broker 401 order attempts.
        """
        if not self.require_auth_session:
            self._cached_auth_ok = True
            return True

        now_ts = time_module.time()
        if (
            not force
            and self._last_auth_status_check_ts
            and (now_ts - self._last_auth_status_check_ts) < self.auth_status_refresh_sec
        ):
            return self._cached_auth_ok

        self._last_auth_status_check_ts = now_ts
        try:
            req = urllib_request.Request(
                self.auth_status_url,
                headers={"Accept": "application/json"},
                method="GET",
            )
            with urllib_request.urlopen(req, timeout=self.auth_status_timeout_sec) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            ok = bool(payload.get("authenticated") or payload.get("logged_in"))
            self._cached_auth_ok = ok
            if ok:
                self._auth_warned = False
            return ok
        except (urllib_error.URLError, ValueError, OSError) as e:
            if self.auth_status_fail_open:
                logger.warning(f"Auth status check failed (fail-open): {e}")
                self._cached_auth_ok = True
                return True
            logger.warning(f"Auth status check failed (fail-closed): {e}")
            self._cached_auth_ok = False
            return False

    def can_trade_with_auth(self, force=False):
        if self.refresh_auth_status(force=force):
            return True
        if not self._auth_warned:
            logger.warning(
                "Trading blocked: /auth/session-status is not authenticated. Refresh Dhan login first."
            )
            self._auth_warned = True
        return False

    def _market_exchange(self):
        return "MCX" if self.segment == "MCX" else "NSE"

    def _order_exchange(self):
        if self.segment == "MCX":
            return "MCX"
        if self.segment == "FNO_OPTIONS":
            return "NFO"
        return "NSE"

    def _quote_exchange(self):
        if self.segment == "MCX":
            return "MCX"
        if self.segment == "FNO_OPTIONS":
            # This runner resolves option tradingsymbols (NFO contracts), so quotes must use NFO.
            return "NFO"
        return "NSE"

    def _api_search_symbol(self, instrument, exchange):
        """Resolve a tradingsymbol using OpenAlgo search API."""
        if not self.client:
            return None
        url = f"{self.client.host}/api/v1/search"
        payload = {
            "apikey": SESSION_CONFIG.get("api_key"),
            "query": instrument,
            "exchange": exchange,
        }
        try:
            import httpx

            response = httpx.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                return None
            data = response.json()
            rows = data.get("data", [])
            if not rows:
                return None

            if exchange == "MCX":
                fut_rows = [
                    r for r in rows if str(r.get("instrumenttype", "")).upper() == "FUT"
                ]
                if fut_rows:
                    # Prefer nearest expiry.
                    def _exp_key(row):
                        raw = row.get("expiry") or "31-DEC-99"
                        try:
                            return datetime.strptime(raw, "%d-%b-%y")
                        except ValueError:
                            return datetime.max

                    fut_rows.sort(key=_exp_key)
                    return fut_rows[0].get("symbol")

            if exchange == "NFO":
                # Prefer nearest-expiry option contracts for current tradable series.
                opt_rows = [
                    r
                    for r in rows
                    if str(r.get("instrumenttype", "")).upper() in ("CE", "PE")
                ]
                if opt_rows:
                    root = str(instrument or "").upper()
                    root_rows = [
                        r
                        for r in opt_rows
                        if str(r.get("symbol", "")).upper().startswith(root)
                    ]
                    if root_rows:
                        opt_rows = root_rows

                    def _exp_key(row):
                        raw = row.get("expiry") or "31-DEC-99"
                        try:
                            return datetime.strptime(raw, "%d-%b-%y")
                        except ValueError:
                            return datetime.max

                    opt_rows.sort(key=_exp_key)
                    return opt_rows[0].get("symbol")

            for row in rows:
                if str(row.get("symbol", "")).upper() == instrument.upper():
                    return row.get("symbol")
            return rows[0].get("symbol")
        except Exception:
            return None

    def _recent_completed_symbol(self, instrument):
        """
        Prefer a symbol that has already filled today for the same underlying.
        This helps avoid repeatedly selecting strikes that brokers are rejecting.
        """
        if not self.client or self.segment != "FNO_OPTIONS":
            return None
        try:
            ob = self.client.orderbook()
            orders = ((ob or {}).get("data") or {}).get("orders") or []
            # Newest first
            for row in orders:
                if str(row.get("exchange", "")).upper() != "NFO":
                    continue
                if str(row.get("order_status", "")).lower() != "complete":
                    continue
                sym = str(row.get("symbol", "")).upper()
                if sym.startswith(instrument.upper()):
                    return sym
            # Fallback: if no completed order found, use an existing open position
            # for the same underlying to avoid idle loops under FNO_ACCEPTED_ONLY.
            pb = self.client.positionbook()
            pdata = (pb or {}).get("data")
            positions = pdata if isinstance(pdata, list) else ((pdata or {}).get("net_position") or [])
            for row in positions:
                if str(row.get("exchange", "")).upper() != "NFO":
                    continue
                qty = float(row.get("quantity", 0) or 0)
                if qty == 0:
                    continue
                sym = str(row.get("symbol", "")).upper()
                if sym.startswith(instrument.upper()):
                    return sym
        except Exception:
            return None
        return None

    def resolve_tradable_symbol(self, instrument):
        """
        Resolve configured instrument (e.g. CRUDEOIL) to tradingsymbol
        (e.g. CRUDEOIL19FEB26FUT) before quotes/orders.
        """
        if instrument in self.resolved_symbols:
            return self.resolved_symbols[instrument]

        resolved = instrument
        order_exchange = self._order_exchange()
        quote_exchange = self._quote_exchange()

        if self.segment == "FNO_OPTIONS":
            require_completed = _env_bool(
                "OA_FNO_ACCEPTED_ONLY", bool(STRATEGY_PARAMS.get("FNO_ACCEPTED_ONLY", False))
            )
            # 1) Use known-good recently completed symbols first.
            completed_candidate = self._recent_completed_symbol(instrument)
            if completed_candidate:
                resolved = completed_candidate
            elif require_completed:
                logger.warning(
                    f"Skipping {instrument}: no recently completed accepted symbol found (FNO_ACCEPTED_ONLY)"
                )
                return None

            # For options, always prefer live API search over local master mapping
            # so we avoid stale far-expiry symbols.
            api_candidate = self._api_search_symbol(instrument, order_exchange)
            if api_candidate and resolved == instrument:
                resolved = api_candidate

        elif self.symbol_resolver:
            try:
                if self.segment == "MCX":
                    candidate = self.symbol_resolver.resolve(
                        {"type": "FUT", "underlying": instrument, "exchange": "MCX"}
                    )
                    if candidate:
                        resolved = candidate
                elif self.segment == "EQUITY":
                    candidate = self.symbol_resolver.resolve(
                        {"type": "EQUITY", "underlying": instrument, "exchange": "NSE"}
                    )
                    if candidate:
                        resolved = candidate
            except Exception as e:
                logger.warning(f"SymbolResolver failed for {instrument}: {e}")

        # Fallback to /api/v1/search if local resolver didn't translate.
        if resolved == instrument:
            api_candidate = self._api_search_symbol(instrument, order_exchange)
            if api_candidate:
                resolved = api_candidate

        self.resolved_symbols[instrument] = {
            "symbol": resolved,
            "order_exchange": order_exchange,
            "quote_exchange": quote_exchange,
        }
        if resolved != instrument:
            logger.info(f"Resolved {instrument} -> {resolved} ({order_exchange})")
        return self.resolved_symbols[instrument]

    def calculate_order_quantity(self, instrument, ltp):
        """Derive quantity from config position size and lot size."""
        if not ltp or ltp <= 0:
            return 0

        target_value = self.segment_config.get("position_size", 25000)
        raw_qty = max(1, int(target_value / ltp))
        max_order_qty = int(self.segment_config.get("max_order_quantity", 0) or 0)

        lot_size = 1
        instruments = self.segment_config.get("instruments", {})
        if isinstance(instruments, dict) and instrument in instruments:
            lot_size = max(1, int(instruments[instrument].get("lot_size", 1)))
            max_order_qty = int(instruments[instrument].get("max_order_quantity", max_order_qty) or 0)

        # Round down to lot size for derivatives.
        if lot_size > 1:
            lots = max(1, raw_qty // lot_size)
            qty = lots * lot_size
        else:
            qty = raw_qty

        # Hard cap order quantity if configured.
        if max_order_qty > 0:
            if lot_size > 1:
                capped_lots = max(1, max_order_qty // lot_size)
                max_order_qty = capped_lots * lot_size
            qty = min(qty, max_order_qty)

        return qty

    def has_open_position(self, symbol):
        return any(p["symbol"] == symbol for p in self.positions)

    def has_broker_open_position(self, symbol):
        """Check live broker positionbook for open quantity in this symbol."""
        if not self.client:
            return False
        try:
            pb = self.client.positionbook() or {}
            pdata = pb.get("data")
            rows = pdata if isinstance(pdata, list) else ((pdata or {}).get("net_position") or [])
            for row in rows:
                sym = str(row.get("symbol", "")).strip().upper()
                if sym != str(symbol).strip().upper():
                    continue
                qty = float(row.get("quantity", 0) or 0)
                if qty != 0:
                    return True
        except Exception:
            return False
        return False

    def get_broker_position_qty(self, symbol):
        """Return live broker net quantity for a symbol; positive long, negative short."""
        if not self.client:
            return 0.0
        try:
            pb = self.client.positionbook() or {}
            pdata = pb.get("data")
            rows = pdata if isinstance(pdata, list) else ((pdata or {}).get("net_position") or [])
            for row in rows:
                sym = str(row.get("symbol", "")).strip().upper()
                if sym != str(symbol).strip().upper():
                    continue
                return float(row.get("quantity", 0) or 0)
        except Exception:
            return 0.0
        return 0.0

    def _allow_position_flip(self):
        seg_key = f"OA_ALLOW_POSITION_FLIP_{self.segment}"
        if os.getenv(seg_key) is not None:
            return _env_bool(seg_key, False)
        if os.getenv("OA_ALLOW_POSITION_FLIP") is not None:
            return _env_bool("OA_ALLOW_POSITION_FLIP", False)
        # Default: allow flips for derivatives where direction changes are common.
        return self.segment in ("MCX", "FNO_OPTIONS")

    def can_take_action(self, symbol, action, allow_add=False):
        """
        Validate whether action can be placed considering current live position.
        - no position: allow
        - allow_add: allow
        - flip mode: allow only opposite-side action to reverse direction
        """
        qty = self.get_broker_position_qty(symbol)
        if qty == 0:
            return True
        if allow_add:
            return True
        if not self._allow_position_flip():
            return False
        side = str(action or "").upper()
        if side == "BUY" and qty < 0:
            return True
        if side == "SELL" and qty > 0:
            return True
        return False

    def choose_bootstrap_action(self, instrument, symbol, ltp, prev_ltp=None, quote=None, loop_count=0):
        """
        Pick startup entry side without long-only bias.
        Env:
          OA_BOOTSTRAP_SIDE[_<SEGMENT>]=AUTO|BUY|SELL
          OA_BOOTSTRAP_MIN_MOVE_PCT=0.01
        """
        seg_key = f"OA_BOOTSTRAP_SIDE_{self.segment}"
        mode = (
            os.getenv(seg_key)
            or os.getenv("OA_BOOTSTRAP_SIDE")
            or "AUTO"
        )
        mode = str(mode).strip().upper()
        if mode in ("BUY", "SELL"):
            return mode

        min_move_pct = float(os.getenv("OA_BOOTSTRAP_MIN_MOVE_PCT", "0.01")) / 100.0

        # If we have a recent price, follow immediate micro-momentum.
        if prev_ltp and prev_ltp > 0:
            move = (float(ltp) - float(prev_ltp)) / float(prev_ltp)
            if move >= min_move_pct:
                return "BUY"
            if move <= -min_move_pct:
                return "SELL"

        # If quote provides an open/prev-close baseline, use that.
        baseline = None
        if isinstance(quote, dict):
            for key in ("open", "open_price", "prev_close", "previous_close", "close"):
                try:
                    value = float(quote.get(key, 0) or 0)
                except Exception:
                    value = 0
                if value > 0:
                    baseline = value
                    break
        if baseline and ltp:
            if float(ltp) > baseline:
                return "BUY"
            if float(ltp) < baseline:
                return "SELL"

        # Last resort: alternate deterministically to avoid one-side clustering.
        token = f"{instrument}:{symbol}:{loop_count}"
        return "BUY" if (sum(ord(ch) for ch in token) % 2 == 0) else "SELL"

    def get_quote_with_fallback(self, symbol, exchange=None, max_retries=0):
        """
        Fetch quote from OpenAlgo API first, then fall back to direct Dhan quote API.
        Returns normalized quote dict with at least 'ltp' on success, else None.
        """
        ex = str(exchange or self._quote_exchange()).strip().upper()
        now_ts = time_module.time()

        if (
            self.client
            and not self.direct_quotes_only
            and now_ts >= self._openalgo_quote_skip_until
        ):
            try:
                quote = self.client.get_quote(symbol, exchange=ex, max_retries=max_retries)
            except Exception:
                quote = None

            if quote and "ltp" in quote:
                try:
                    if float(quote.get("ltp", 0) or 0) > 0:
                        self._openalgo_quote_failures = 0
                        self._openalgo_quote_skip_until = 0.0
                        return quote
                except Exception:
                    # keep fallback path alive on malformed ltp
                    pass
                # keep existing behavior if ltp is present but non-positive
                return quote

            self._openalgo_quote_failures += 1
            fail_threshold = int(os.getenv("OA_OPENALGO_QUOTE_FAIL_THRESHOLD", "3"))
            cooldown_sec = float(os.getenv("OA_OPENALGO_QUOTE_COOLDOWN_SEC", "120"))
            if self._openalgo_quote_failures >= max(1, fail_threshold):
                self._openalgo_quote_skip_until = now_ts + max(1.0, cooldown_sec)
                logger.warning(
                    f"OpenAlgo quote unstable; using direct Dhan quotes for next {cooldown_sec:.0f}s"
                )

        if not self.dhan_data:
            return None

        try:
            quote = self.dhan_data.get_quotes(symbol, ex)
            if isinstance(quote, dict) and float(quote.get("ltp", 0) or 0) > 0:
                key = f"{ex}:{symbol}"
                if key not in self._dhan_fallback_logged:
                    logger.info(f"📡 Using direct Dhan quote fallback for {symbol} ({ex})")
                    self._dhan_fallback_logged.add(key)
                return quote
        except Exception as e:
            logger.debug(f"Dhan direct quote failed for {symbol} ({ex}): {e}")

        return None

    def check_risk_limits(self):
        """Check if we hit daily loss limit"""
        max_daily_loss = self.get_max_daily_loss_abs()

        if self.daily_pnl <= -max_daily_loss:
            logger.error(f"🚨 MAX LOSS HIT: ₹{self.daily_pnl}")
            self.persist_daily_lock(
                f"Max daily loss hit: pnl={self.daily_pnl:.2f} limit={-max_daily_loss:.2f}"
            )
            return False
        return True

    def maybe_lock_on_broker_auth_error(self, payload):
        """
        Stop new entries when broker reports expired/invalid auth.
        Avoids hammering placeorder with guaranteed 401 failures.
        """
        txt = str(payload or "").lower()
        auth_markers = (
            "invalid or expired",
            "access token is invalid",
            "authentication failed",
            "client id or user generated access token is invalid",
        )
        if any(marker in txt for marker in auth_markers):
            if not self.trailing_lock_triggered:
                self.trailing_lock_triggered = True
                self.trailing_lock_reason = (
                    "Broker access token expired/invalid. Refresh Dhan login before trading."
                )
                logger.error(f"🔒 AUTH LOCK: {self.trailing_lock_reason}")
            self.persist_daily_lock(self.trailing_lock_reason)
            return True
        return False

    def check_profit_target(self):
        """Check if we hit profit target"""
        profit_target = self.get_profit_target_abs()
        if self.daily_pnl >= profit_target:
            logger.info(f"🎯 PROFIT TARGET HIT: ₹{self.daily_pnl}")
            if _env_bool("OA_LOCK_ON_PROFIT_TARGET", True):
                self.persist_daily_lock(
                    f"Profit target hit: pnl={self.daily_pnl:.2f} target={profit_target:.2f}"
                )
            return True
        return False

    def get_profit_target_abs(self):
        """Return configured absolute profit target with optional segment override."""
        seg_key = f"OA_DAILY_PROFIT_TARGET_ABS_{self.segment}"
        raw = os.getenv(seg_key, os.getenv("OA_DAILY_PROFIT_TARGET_ABS"))
        try:
            if raw is not None:
                return float(raw)
        except Exception:
            pass
        return float(RISK_CONFIG["DAILY_PROFIT_TARGET"])

    def get_max_daily_loss_abs(self):
        """Return configured absolute max daily loss with optional segment override."""
        seg_key = f"OA_MAX_DAILY_LOSS_ABS_{self.segment}"
        raw = os.getenv(seg_key, os.getenv("OA_MAX_DAILY_LOSS_ABS"))
        try:
            if raw is not None:
                return float(raw)
        except Exception:
            pass
        return float(RISK_CONFIG["MAX_DAILY_LOSS"])

    def is_market_open_now(self):
        """Check if market is open for this segment"""
        return is_market_open(self._market_exchange())

    def can_place_trade(self):
        """Check if we can place a new trade"""
        if self.trailing_lock_triggered:
            if not self._lock_warned:
                logger.warning(f"Trading locked: {self.trailing_lock_reason}")
                self._lock_warned = True
            return False
        if not self.can_trade_with_auth(force=False):
            return False
        # Check market status
        if not self.is_market_open_now():
            logger.warning(f"Market ({self.segment}) closed or not open yet")
            return False

        # Refresh broker MTM before daily-limit checks so stale in-memory PnL
        # cannot permit extra entries after a loss breach.
        self.refresh_pnl_for_pretrade_gate(force=False)

        # Check daily limits
        if not self.check_risk_limits():
            return False

        # Check max trades per segment
        max_trades = self.segment_config.get("max_trades_per_day", 5)
        if self.trades_today >= max_trades:
            logger.warning(f"Max trades ({max_trades}) reached for {self.segment}")
            return False

        return True

    def evaluate_trailing_profit_lock(self):
        """
        Lock further trading if profit retraces from peak beyond configured threshold.
        Env controls:
          OA_TRAIL_LOCK_ENABLE=true|false
          OA_TRAIL_LOCK_ACTIVATE_PNL=10000
          OA_TRAIL_LOCK_DRAWDOWN=3000
        """
        if self.trailing_lock_triggered:
            return True
        if not _env_bool("OA_TRAIL_LOCK_ENABLE", False):
            return False

        seg_activate_key = f"OA_TRAIL_LOCK_ACTIVATE_PNL_{self.segment}"
        seg_drawdown_key = f"OA_TRAIL_LOCK_DRAWDOWN_{self.segment}"
        activate_pnl = float(
            os.getenv(seg_activate_key, os.getenv("OA_TRAIL_LOCK_ACTIVATE_PNL", "10000"))
        )
        drawdown_lock = float(
            os.getenv(seg_drawdown_key, os.getenv("OA_TRAIL_LOCK_DRAWDOWN", "3000"))
        )

        self.peak_pnl = max(self.peak_pnl, float(self.daily_pnl))
        if self.peak_pnl < activate_pnl:
            return False

        dd = self.peak_pnl - float(self.daily_pnl)
        if dd >= drawdown_lock:
            self.trailing_lock_triggered = True
            self.trailing_lock_reason = (
                f"Peak ₹{self.peak_pnl:.2f} -> Current ₹{self.daily_pnl:.2f} "
                f"(DD ₹{dd:.2f} >= ₹{drawdown_lock:.2f})"
            )
            logger.error(f"🔒 TRAILING PROFIT LOCK: {self.trailing_lock_reason}")
            self.persist_daily_lock(f"Trailing lock: {self.trailing_lock_reason}")
            return True
        return False

    def square_off_open_positions(self):
        """
        Attempt to flatten broker positions by sending opposite MARKET orders.
        Best-effort only; logs failures and continues.
        """
        if not self.client:
            return
        try:
            pb = self.client.positionbook() or {}
            pdata = pb.get("data")
            rows = pdata if isinstance(pdata, list) else ((pdata or {}).get("net_position") or [])
            for row in rows:
                qty = int(float(row.get("quantity", 0) or 0))
                if qty == 0:
                    continue
                symbol = str(row.get("symbol", "")).strip()
                exchange = str(row.get("exchange", "")).strip().upper() or self._order_exchange()
                action = "SELL" if qty > 0 else "BUY"
                order_qty = abs(qty)
                try:
                    max_chunk = int(float(os.getenv("OA_SQUAREOFF_MAX_CHUNK_QTY", "0")))
                except Exception:
                    max_chunk = 0

                if max_chunk > 0 and order_qty > max_chunk:
                    chunks = []
                    remaining = order_qty
                    while remaining > 0:
                        leg = min(max_chunk, remaining)
                        chunks.append(leg)
                        remaining -= leg
                else:
                    chunks = [order_qty]

                for chunk in chunks:
                    try:
                        logger.warning(f"Square-off: {action} {symbol} qty={chunk} ({exchange})")
                        if hasattr(self.client, "placeorder"):
                            resp = self.client.placeorder(
                                strategy="TrailProfitLock",
                                symbol=symbol,
                                action=action,
                                exchange=exchange,
                                price_type=SESSION_CONFIG.get("ORDER_TYPE", "MARKET"),
                                product=SESSION_CONFIG.get("PRODUCT_TYPE", "MIS"),
                                quantity=chunk,
                            )
                        else:
                            resp = self.client.placesmartorder(
                                strategy="TrailProfitLock",
                                symbol=symbol,
                                action=action,
                                exchange=exchange,
                                price_type=SESSION_CONFIG.get("ORDER_TYPE", "MARKET"),
                                product=SESSION_CONFIG.get("PRODUCT_TYPE", "MIS"),
                                quantity=chunk,
                                position_size=0,
                            )
                        logger.warning(f"Square-off response for {symbol}: {resp}")
                    except Exception as e:
                        logger.error(f"Square-off failed for {symbol} (qty={chunk}): {e}")
        except Exception as e:
            logger.error(f"Square-off scan failed: {e}")

    def place_trade(
        self,
        symbol,
        quantity,
        entry_price,
        trade_type="BUY",
        exchange=None,
        source_symbol=None,
    ):
        """Place a trade with risk management"""
        # Force a fresh MTM snapshot immediately before order-gate checks.
        self.refresh_pnl_for_pretrade_gate(force=True)
        if not self.can_place_trade():
            return None

        side = str(trade_type).upper()
        is_buy = side == "BUY"

        # Calculate stop loss
        if self.segment == "EQUITY":
            sl_pct = RISK_CONFIG["EQUITY_STOP_LOSS_PERCENT"] / 100
            tp_pct = RISK_CONFIG["TAKE_PROFIT_PERCENT"] / 100
            if is_buy:
                stop_loss = entry_price * (1 - sl_pct)
                target = entry_price * (1 + tp_pct)
            else:
                stop_loss = entry_price * (1 + sl_pct)
                target = entry_price * (1 - tp_pct)
        elif self.segment == "FNO_OPTIONS":
            if is_buy:
                stop_loss = entry_price * 0.5  # 50% stop loss
                target = entry_price * 2  # 100% target
            else:
                stop_loss = entry_price * 1.5
                target = entry_price * 0.5
        else:  # MCX
            sl_pct = RISK_CONFIG["MCX_STOP_LOSS_PERCENT"] / 100
            tp_pct = RISK_CONFIG["MCX_TAKE_PROFIT_PERCENT"] / 100
            if is_buy:
                stop_loss = entry_price * (1 - sl_pct)
                target = entry_price * (1 + tp_pct)
            else:
                stop_loss = entry_price * (1 + sl_pct)
                target = entry_price * (1 - tp_pct)

        trade = {
            "symbol": symbol,
            "quantity": quantity,
            "entry_price": entry_price,
            "stop_loss": round(stop_loss, 2),
            "target": round(target, 2),
            "type": trade_type,
            "timestamp": datetime.now().isoformat(),
            "segment": self.segment,
            "source_symbol": source_symbol or symbol,
        }

        # Execute Live Trade if configured
        if SESSION_CONFIG.get("session_type") == "live" and self.client:
            try:
                exchange = exchange or self._order_exchange()
                product = SESSION_CONFIG.get("PRODUCT_TYPE", "MIS")
                force_direct = _env_bool("OA_FORCE_DIRECT_ORDER", False)
                if self.segment == "FNO_OPTIONS":
                    force_direct = _env_bool("OA_FNO_FORCE_DIRECT_ORDER", force_direct)
                elif self.segment == "MCX":
                    # Smart-order target-position semantics can suppress opposite-side
                    # execution ("Positions Already Matched"), so prefer direct orders.
                    force_direct = _env_bool("OA_MCX_FORCE_DIRECT_ORDER", True)

                logger.info(f"🚀 Executing LIVE {trade_type} Order for {symbol}...")
                if force_direct and hasattr(self.client, "placeorder"):
                    response = self.client.placeorder(
                        strategy="ProductionStrategy",
                        symbol=symbol,
                        action=trade_type,
                        exchange=exchange,
                        price_type=SESSION_CONFIG.get("ORDER_TYPE", "MARKET"),
                        product=product,
                        quantity=quantity,
                    )
                else:
                    response = self.client.placesmartorder(
                        strategy="ProductionStrategy",
                        symbol=symbol,
                        action=trade_type,
                        exchange=exchange,
                        price_type=SESSION_CONFIG.get("ORDER_TYPE", "MARKET"),
                        product=product,
                        quantity=quantity,
                        position_size=quantity,
                    )
                logger.info(f"Order Response: {response}")
                if response and str(response.get("status", "")).lower() == "success":
                    # Smart-order can return success with "No Action needed" when
                    # target position already matches. Do not count it as a new trade.
                    msg = str(response.get("message", "")).lower()
                    if "no action needed" in msg or "positions already matched" in msg:
                        logger.info(f"No new order executed for {symbol}: {response.get('message')}")
                        return None
                    trade["order_id"] = response.get("order_id") or response.get("orderid") or "simulated"
                else:
                    self.maybe_lock_on_broker_auth_error(response)
                    logger.error(f"Order rejected for {symbol}: {response}")
                    return None
            except Exception as e:
                self.maybe_lock_on_broker_auth_error(e)
                logger.error(f"Failed to place live order: {e}")
                return None

        self.positions.append(trade)
        self.trades_today += 1

        logger.info(f"✅ Trade placed: {trade_type} {symbol} @ ₹{entry_price}")
        logger.info(f"   SL: ₹{stop_loss:.2f} | Target: ₹{target:.2f}")

        return trade

    def update_pnl(self, current_prices):
        """Update P&L based on current prices"""
        total_pnl = 0
        for pos in self.positions:
            symbol = pos["symbol"]
            if symbol in current_prices:
                current_price = current_prices[symbol]
                entry = pos["entry_price"]
                qty = pos["quantity"]

                if pos["type"] == "BUY":
                    pnl = (current_price - entry) * qty
                else:
                    pnl = (entry - current_price) * qty

                total_pnl += pnl

        self.daily_pnl = total_pnl
        return total_pnl

    def _segment_matches_dhan_exchange(self, exchange_segment):
        """Map Dhan exchangeSegment to this runner segment."""
        ex = str(exchange_segment or "").upper()
        if self.segment == "FNO_OPTIONS":
            return "FNO" in ex
        if self.segment == "MCX":
            return "MCX" in ex
        return ex in ("NSE_EQ", "BSE_EQ")

    def update_pnl_from_dhan_raw_positions(self):
        """
        Derive MTM from Dhan raw /v2/positions using realized+unrealized PnL.
        This avoids quote dependency for PnL tracking and trailing lock logic.

        Env controls:
          OA_USE_DHAN_RAW_MTM=true|false
          OA_DHAN_POS_TIMEOUT_SEC=5
        """
        if not _env_bool("OA_USE_DHAN_RAW_MTM", True):
            return None

        token = (os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
        if not token:
            return None

        try:
            import httpx

            base_url = os.getenv("OA_DHAN_BASE_URL", "https://api.dhan.co").rstrip("/")
            timeout_sec = float(os.getenv("OA_DHAN_POS_TIMEOUT_SEC", "5"))
            headers = {
                "access-token": token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            response = httpx.get(
                f"{base_url}/v2/positions",
                headers=headers,
                timeout=timeout_sec,
            )
            if response.status_code != 200:
                logger.warning(
                    f"Dhan raw MTM unavailable (HTTP {response.status_code}); falling back to quote-based MTM"
                )
                return None

            rows = response.json()
            if not isinstance(rows, list):
                return None

            realized = 0.0
            unrealized = 0.0
            used_rows = 0
            include_flat = _env_bool("OA_DHAN_MTM_INCLUDE_FLAT", False)

            for row in rows:
                if not isinstance(row, dict):
                    continue
                if not self._segment_matches_dhan_exchange(row.get("exchangeSegment")):
                    continue
                qty = float(row.get("netQty", 0) or 0)
                if qty == 0 and not include_flat:
                    continue
                realized += float(row.get("realizedProfit", 0) or 0)
                unrealized += float(row.get("unrealizedProfit", 0) or 0)
                used_rows += 1

            if used_rows == 0:
                return None

            self.daily_pnl = float(realized + unrealized)
            logger.info(
                f"📊 Dhan MTM | {self.segment} | PnL: ₹{self.daily_pnl:.2f} | "
                f"realized={realized:.2f} unrealized={unrealized:.2f} rows={used_rows}"
            )
            return self.daily_pnl
        except Exception as e:
            logger.warning(f"Dhan raw MTM failed ({e}); falling back to quote-based MTM")
            return None

    def update_pnl_from_broker_positions(self):
        """
        Derive MTM directly from broker positionbook.
        Uses fresh quotes when available; falls back to last seen quote per symbol.
        """
        if not self.client:
            return self.daily_pnl
        try:
            raw_mtm = self.update_pnl_from_dhan_raw_positions()
            if raw_mtm is not None:
                return raw_mtm

            pb = self.client.positionbook() or {}
            pdata = pb.get("data")
            rows = pdata if isinstance(pdata, list) else ((pdata or {}).get("net_position") or [])

            total_pnl = 0.0
            quoted = 0
            stale = 0
            for row in rows:
                qty = float(row.get("quantity", 0) or 0)
                if qty == 0:
                    continue
                symbol = str(row.get("symbol", "")).strip()
                if not symbol:
                    continue
                exchange = str(row.get("exchange", "")).strip().upper() or self._quote_exchange()
                avg = float(row.get("average_price", 0) or 0)

                ltp = None
                q = self.get_quote_with_fallback(symbol, exchange=exchange, max_retries=0)
                if q and "ltp" in q:
                    try:
                        ltp = float(q.get("ltp"))
                    except Exception:
                        ltp = None
                if ltp is not None and ltp > 0:
                    self.last_symbol_prices[symbol] = ltp
                    quoted += 1
                else:
                    ltp = self.last_symbol_prices.get(symbol)
                    if ltp is not None:
                        stale += 1
                if ltp is None:
                    continue

                total_pnl += (ltp - avg) * qty

            self.daily_pnl = float(total_pnl)
            logger.info(
                f"📊 Broker MTM | {self.segment} | PnL: ₹{self.daily_pnl:.2f} | quoted={quoted} stale={stale}"
            )
            return self.daily_pnl
        except Exception as e:
            logger.error(f"Broker MTM update failed: {e}")
            return self.daily_pnl

    def get_status(self):
        """Get current trading session status"""
        return {
            "segment": self.segment,
            "daily_pnl": self.daily_pnl,
            "positions": len(self.positions),
            "trades_today": self.trades_today,
            "profit_target": self.get_profit_target_abs(),
            "max_loss": -self.get_max_daily_loss_abs(),
            "can_trade": self.can_place_trade(),
            "start_time": self.start_time.isoformat(),
            "market_open": self.is_market_open_now(),
        }


def run_strategy(segment="EQUITY"):
    """Single-pass status check for a segment."""
    logger.info(f"🚀 Starting {segment} Strategy")

    session = TradingSession(segment)

    # Check if market is open
    if not session.is_market_open_now():
        logger.warning(f"Market for {segment} is CLOSED.")
        return session.get_status()

    logger.info(f"   Target: ₹{RISK_CONFIG['DAILY_PROFIT_TARGET']:,}")
    logger.info(f"   Max Loss: ₹{RISK_CONFIG['MAX_DAILY_LOSS']:,}")

    # Get instruments for the segment
    instruments = session.segment_config.get("instruments", {})

    if segment == "FNO_OPTIONS":
        instruments_list = list(instruments.keys())
    elif isinstance(instruments, dict):
        instruments_list = list(instruments.keys())
    else:
        instruments_list = instruments

    logger.info(f"📱 Monitoring instruments: {instruments_list}")

    if session.client:
        try:
            resolved = session.resolve_tradable_symbol(instruments_list[0])
            if not resolved:
                logger.warning(f"No tradable symbol resolved for {instruments_list[0]}")
                return session.get_status()
            quote = session.get_quote_with_fallback(
                resolved["symbol"], exchange=resolved["quote_exchange"], max_retries=0
            )
            if quote:
                logger.info(
                    f"📡 Data Feed Active: {resolved['symbol']} LTP = {quote.get('ltp')}"
                )
            else:
                logger.warning(
                    f"⚠️ Could not fetch quote for {instruments_list[0]} ({resolved['symbol']})"
                )
        except Exception as e:
            logger.error(f"Error checking data feed: {e}")

    return session.get_status()


def run_live_strategy(segment="EQUITY", iterations=None):
    """
    Run live strategy loop.
    - Resolves symbols before quote/order
    - Polls quotes continuously
    - Places momentum-based orders when threshold is crossed
    """
    logger.info(f"🚀 Starting LIVE {segment} Strategy Loop")
    session = TradingSession(segment)
    if session.trailing_lock_triggered and _env_bool("OA_EXIT_ON_LOCKED_START", True):
        logger.error(
            f"Start blocked for {segment}: {session.trailing_lock_reason}"
        )
        return session.get_status()
    if not session.can_trade_with_auth(force=True):
        logger.error(f"Start blocked for {segment}: broker auth/session is not authenticated.")
        return session.get_status()

    # Seed risk checks with broker MTM before the first entry cycle.
    session.refresh_pnl_for_pretrade_gate(force=True)
    if not session.check_risk_limits():
        logger.error(
            f"Start blocked for {segment}: daily loss threshold already breached (pnl={session.daily_pnl:.2f})"
        )
        return session.get_status()

    instruments = session.segment_config.get("instruments", {})
    instruments_list = list(instruments.keys()) if isinstance(instruments, dict) else instruments

    if not instruments_list:
        logger.error(f"No instruments configured for {segment}")
        return session.get_status()

    # Optional instrument filter via env, useful for focused aggressive runs.
    # Example: OA_FNO_ACTIVE_INSTRUMENTS=BANKNIFTY
    active_override = os.getenv(f"OA_{segment}_ACTIVE_INSTRUMENTS") or os.getenv(
        "OA_ACTIVE_INSTRUMENTS"
    )
    if active_override:
        requested = [x.strip().upper() for x in active_override.split(",") if x.strip()]
        existing = {str(x).upper(): x for x in instruments_list}
        selected = [existing.get(sym, sym) for sym in requested]
        if selected:
            instruments_list = selected

    api_interval = str(session.segment_config.get("api_interval", "1minute")).lower()
    interval_map = {
        "1minute": 60,
        "3minute": 180,
        "5minute": 300,
        "15minute": 900,
    }
    sleep_seconds = interval_map.get(api_interval, 60)
    # Optional per-segment loop override for faster live cycling.
    # Example: OA_LOOP_SECONDS_FNO_OPTIONS=20
    override = os.getenv(f"OA_LOOP_SECONDS_{segment}")
    if override is None:
        override = os.getenv("OA_LOOP_SECONDS")
    try:
        if override is not None and float(override) > 0:
            sleep_seconds = int(float(override))
    except ValueError:
        pass
    entry_threshold_pct = float(
        os.getenv(
            "OA_MOMENTUM_ENTRY_PERCENT",
            str(STRATEGY_PARAMS.get("MOMENTUM_ENTRY_PERCENT", 0.15)),
        )
    )  # 0.15%
    bootstrap_trades = int(
        os.getenv(
            f"OA_BOOTSTRAP_TRADES_{segment}",
            os.getenv("OA_BOOTSTRAP_TRADES", "0"),
        )
    )

    loop_count = 0
    returns_window = []
    allow_add = segment == "FNO_OPTIONS" and _env_bool("OA_FNO_ALLOW_ADD", False)
    blind_add_every = int(os.getenv("OA_FNO_BLIND_ADD_EVERY_LOOPS", "3"))
    disable_agent = _env_bool("OA_AGENT_DISABLE", False)
    while True:
        loop_count += 1
        if not session.is_market_open_now():
            logger.warning(f"Market for {segment} is CLOSED. Sleeping {sleep_seconds}s.")
            time_module.sleep(sleep_seconds)
            if iterations and loop_count >= iterations:
                break
            continue

        active_instruments = list(instruments_list)
        if (not disable_agent) and get_agent_client and DecisionRequest:
            try:
                client = get_agent_client()
                realized_vol = 0.3
                if len(returns_window) >= 5:
                    mean = sum(returns_window) / len(returns_window)
                    var = sum((x - mean) ** 2 for x in returns_window) / max(1, (len(returns_window) - 1))
                    realized_vol = max(0.0, (var**0.5) * (len(returns_window) ** 0.5))
                req = DecisionRequest(
                    segment=segment,
                    strategy_id=f"runner_{segment.lower()}",
                    symbol="*",
                    features={
                        "instruments": instruments_list,
                        "realized_vol": realized_vol,
                        "loop_count": loop_count,
                    },
                    context={"trades_today": session.trades_today},
                    constraints={"guardrails_enabled": True},
                )
                d = client.decide(
                    route="/v1/decision/regime-router",
                    request=req,
                    fallback_decision="ROUTE",
                    confidence_override_required=False,
                )
                proposed = d.params.get("active_instruments") if isinstance(d.params, dict) else None
                if isinstance(proposed, list) and proposed:
                    active_instruments = [x for x in proposed if x in instruments_list] or active_instruments
            except Exception as e:
                logger.debug(f"Regime router decision failed: {e}")

        current_prices = {}
        for instrument in active_instruments:
            resolved = session.resolve_tradable_symbol(instrument)
            if not resolved:
                continue
            tradingsymbol = resolved["symbol"]
            quote_exchange = resolved["quote_exchange"]
            order_exchange = resolved["order_exchange"]

            quote = session.get_quote_with_fallback(
                tradingsymbol, exchange=quote_exchange, max_retries=0
            )
            if not quote or "ltp" not in quote:
                logger.warning(f"⚠️ Could not fetch quote for {instrument} ({tradingsymbol})")
                # Aggressive failover mode: attempt controlled startup entries
                # even when quotes are unavailable, to avoid total inactivity.
                blind_mode = _env_bool(
                    f"OA_ALLOW_BLIND_START_ENTRIES_{segment}",
                    _env_bool("OA_ALLOW_BLIND_START_ENTRIES", False),
                )
                blind_price = float(
                    os.getenv(
                        "OA_BLIND_ENTRY_FALLBACK_PRICE",
                        str(STRATEGY_PARAMS.get("BLIND_ENTRY_FALLBACK_PRICE", 100.0)),
                    )
                )
                blind_action = session.choose_bootstrap_action(
                    instrument=instrument,
                    symbol=tradingsymbol,
                    ltp=blind_price,
                    prev_ltp=session.last_prices.get(instrument),
                    quote=None,
                    loop_count=loop_count,
                )
                if (
                    blind_mode
                    and session.segment == "FNO_OPTIONS"
                    and bootstrap_trades > 0
                    and session.trades_today < bootstrap_trades
                    and session.can_place_trade()
                    and (allow_add or tradingsymbol not in session.blind_entry_attempted)
                    and session.can_take_action(
                        tradingsymbol, blind_action, allow_add=allow_add
                    )
                ):
                    lot_size = 1
                    conf = session.segment_config.get("instruments", {})
                    if isinstance(conf, dict) and instrument in conf:
                        lot_size = max(1, int(conf[instrument].get("lot_size", 1)))
                    # Use one-lot sizing in blind mode to avoid oversized reject bursts.
                    qty = lot_size
                    if allow_add:
                        last_loop = session.last_blind_add_loop.get(tradingsymbol, -10**9)
                        if blind_add_every > 0 and (loop_count - last_loop) < blind_add_every:
                            qty = 0
                    if qty > 0:
                        session.blind_entry_attempted.add(tradingsymbol)
                        session.last_blind_add_loop[tradingsymbol] = loop_count
                        session.place_trade(
                            symbol=tradingsymbol,
                            quantity=qty,
                            entry_price=blind_price,
                            trade_type=blind_action,
                            exchange=order_exchange,
                            source_symbol=instrument,
                        )
                continue

            ltp = float(quote["ltp"])
            if ltp <= 0:
                logger.warning(
                    f"⚠️ Non-tradable LTP {ltp} for {instrument} ({tradingsymbol}); skipping quote-driven sizing"
                )
                continue
            current_prices[tradingsymbol] = ltp
            prev_ltp = session.last_prices.get(instrument)
            if prev_ltp and prev_ltp > 0:
                ret = (ltp - prev_ltp) / prev_ltp
                if not math.isnan(ret) and not math.isinf(ret):
                    returns_window.append(float(ret))
                    if len(returns_window) > 60:
                        returns_window = returns_window[-60:]

            # Hard-aggressive startup: force early entries once quotes are available.
            # This bypasses momentum wait and ensures the strategy does not stay idle.
            force_start_loops = int(
                os.getenv(
                    f"OA_FNO_FORCE_START_LOOPS_{segment}",
                    os.getenv("OA_FNO_FORCE_START_LOOPS", "0"),
                )
            )
            force_action = session.choose_bootstrap_action(
                instrument=instrument,
                symbol=tradingsymbol,
                ltp=ltp,
                prev_ltp=prev_ltp,
                quote=quote,
                loop_count=loop_count,
            )
            if (
                segment == "FNO_OPTIONS"
                and loop_count <= force_start_loops
                and session.trades_today < bootstrap_trades
                and session.can_place_trade()
                and session.can_take_action(
                    tradingsymbol, force_action, allow_add=allow_add
                )
            ):
                qty = session.calculate_order_quantity(instrument, ltp)
                logger.info(
                    f"⚡ Force-entry check {instrument} | side={force_action} | loop={loop_count} | ltp={ltp:.2f} | qty={qty} | trades={session.trades_today}/{bootstrap_trades}"
                )
                if qty > 0:
                    session.place_trade(
                        symbol=tradingsymbol,
                        quantity=qty,
                        entry_price=ltp,
                        trade_type=force_action,
                        exchange=order_exchange,
                        source_symbol=instrument,
                    )

            # Aggressive bootstrap: place initial entries on first valid quotes
            # to avoid waiting for a full momentum cycle.
            bootstrap_action = session.choose_bootstrap_action(
                instrument=instrument,
                symbol=tradingsymbol,
                ltp=ltp,
                prev_ltp=prev_ltp,
                quote=quote,
                loop_count=loop_count,
            )
            if (
                prev_ltp is None
                and bootstrap_trades > 0
                and session.trades_today < bootstrap_trades
                and session.can_place_trade()
                and session.can_take_action(
                    tradingsymbol, bootstrap_action, allow_add=allow_add
                )
            ):
                qty = session.calculate_order_quantity(instrument, ltp)
                if qty > 0:
                    session.place_trade(
                        symbol=tradingsymbol,
                        quantity=qty,
                        entry_price=ltp,
                        trade_type=bootstrap_action,
                        exchange=order_exchange,
                        source_symbol=instrument,
                    )

            if prev_ltp and session.can_place_trade():
                threshold = entry_threshold_pct / 100.0
                action = None
                if ltp >= prev_ltp * (1 + threshold):
                    action = "BUY"
                elif ltp <= prev_ltp * (1 - threshold):
                    action = "SELL"

                if action and session.can_take_action(
                    tradingsymbol, action, allow_add=allow_add
                ):
                    qty = session.calculate_order_quantity(instrument, ltp)
                    if qty > 0:
                        session.place_trade(
                            symbol=tradingsymbol,
                            quantity=qty,
                            entry_price=ltp,
                            trade_type=action,
                            exchange=order_exchange,
                            source_symbol=instrument,
                        )

            session.last_prices[instrument] = ltp

        use_broker_mtm = (
            segment in ("FNO_OPTIONS", "MCX")
            and _env_bool("OA_TRAIL_LOCK_USE_BROKER_MTM", True)
        )
        if use_broker_mtm:
            session.update_pnl_from_broker_positions()
            logger.info(
                f"📊 {segment} | Loop #{loop_count} | PnL: ₹{session.daily_pnl:.2f} | Trades: {session.trades_today} | mode=broker_mtm"
            )
        elif current_prices:
            session.update_pnl(current_prices)
            logger.info(
                f"📊 {segment} | Loop #{loop_count} | PnL: ₹{session.daily_pnl:.2f} | Trades: {session.trades_today}"
            )

        if session.evaluate_trailing_profit_lock():
            if _env_bool("OA_TRAIL_LOCK_AUTO_SQUAREOFF", False):
                session.square_off_open_positions()
            logger.info("Stopping loop due to trailing profit lock.")
            break

        hit_target = session.check_profit_target()
        within_risk = session.check_risk_limits()
        if hit_target or not within_risk:
            if (
                not within_risk
                and _env_bool("OA_MAXLOSS_AUTO_SQUAREOFF", False)
            ):
                session.square_off_open_positions()
            logger.info(f"Stopping {segment} loop due to target/risk condition.")
            break

        if iterations and loop_count >= iterations:
            break

        time_module.sleep(sleep_seconds)

    return session.get_status()


def main():
    parser = argparse.ArgumentParser(description="OpenAlgo Strategy Runner")
    parser.add_argument(
        "--segment",
        type=str,
        default="EQUITY",
        choices=["EQUITY", "FNO_OPTIONS", "MCX", "ALL"],
        help="Trading segment",
    )
    parser.add_argument(
        "--action",
        type=str,
        default="status",
        choices=["start", "stop", "status", "test"],
        help="Action to perform",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Number of loop iterations for --action=start (default: run indefinitely)",
    )

    args = parser.parse_args()

    if args.action == "start":
        if args.segment == "ALL":
            for seg in ["EQUITY", "FNO_OPTIONS", "MCX"]:
                # For ALL, default to one pass per segment unless explicitly set.
                segment_iterations = args.iterations if args.iterations is not None else 1
                status = run_live_strategy(seg, iterations=segment_iterations)
                print(f"Status for {seg}: {json.dumps(status, indent=2)}")
        else:
            status = run_live_strategy(args.segment, iterations=args.iterations)
            print(json.dumps(status, indent=2))

    elif args.action == "status":
        session = TradingSession()
        print(json.dumps(session.get_status(), indent=2))

    elif args.action == "test":
        print("🧪 Testing configuration...")
        config_summary = {
            "risk_config": RISK_CONFIG,
            "segment_configs": list(SEGMENT_CONFIGS.keys()),
            "strategy_params": STRATEGY_PARAMS,
        }
        print(json.dumps(config_summary, indent=2))

    logger.info("✅ Done")


if __name__ == "__main__":
    main()
