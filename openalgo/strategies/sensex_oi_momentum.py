#!/usr/bin/env python3
"""
SENSEX OI Momentum (OpenAlgo Web UI Compatible)
Directional options strategy based on OI Walls and PCR analysis.
Buys ATM CE on Put Wall support (PCR > 1.2) or ATM PE on Call Wall resistance (PCR < 0.8).

Exchange: BFO (BSE F&O)
Underlying: SENSEX on BSE_INDEX
Expiry: Weekly Friday
Edge: OI Walls act as strong S/R in BSE markets; uses PCR for confirmation.
"""
import os
import sys
import time
import requests
from datetime import datetime, timedelta, timezone

# Line-buffered output (required for real-time log capture)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
sys.path.insert(0, utils_dir)

try:
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        safe_float,
        safe_int,
    )
    from strategy_common import (
        SignalDebouncer,
        TradeLimiter,
        format_kv,
    )
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# ===========================
# CONFIGURATION - SENSEX OI MOMENTUM
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "sensex_oi_momentum")
UNDERLYING = os.getenv("UNDERLYING", "SENSEX")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "BSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "BFO")
PRODUCT = os.getenv("PRODUCT", "MIS")           # MIS=Intraday
QUANTITY = int(os.getenv("QUANTITY", "1"))        # 1 lot = 10 units for SENSEX
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "15")) # Need wider range for walls

# Strategy Logic Parameters
PCR_BULLISH = float(os.getenv("PCR_BULLISH", "1.2"))
PCR_BEARISH = float(os.getenv("PCR_BEARISH", "0.8"))
WALL_PROXIMITY_PTS = float(os.getenv("WALL_PROXIMITY_PTS", "150.0")) # Points from wall to trigger

# Risk parameters
SL_PCT = float(os.getenv("SL_PCT", "25.0"))      # Tighter SL for directional plays
TP_PCT = float(os.getenv("TP_PCT", "60.0"))       # Aggressive TP for momentum
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "20")) # Short hold time

# Rate limiting
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "180"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "15"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "5"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

# Time Filters
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:30")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")
FRIDAY_EXIT_TIME = os.getenv("FRIDAY_EXIT_TIME", "14:30")

# Manual expiry override (format: 14FEB26)
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

# Defensive normalization: SENSEX/BANKEX trade on BSE
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and UNDERLYING_EXCHANGE.upper() == "NSE_INDEX":
    UNDERLYING_EXCHANGE = "BSE_INDEX"
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and OPTIONS_EXCHANGE.upper() == "NFO":
    OPTIONS_EXCHANGE = "BFO"

# ===========================
# API KEY RETRIEVAL
# ===========================
API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

if not API_KEY:
    try:
        from database.auth_db import get_first_available_api_key
        API_KEY = get_first_available_api_key()
        if API_KEY:
            print("Successfully retrieved API Key from database.", flush=True)
    except Exception as e:
        print(f"Warning: Could not retrieve API key from database: {e}", flush=True)

if not API_KEY:
    raise ValueError("API Key must be set in OPENALGO_APIKEY environment variable")


# Local fallback for is_market_open to avoid dependencies
def is_market_open_local():
    """Checks if market is open (9:15 - 15:30 IST)."""
    try:
        # IST = UTC + 5:30
        utc_now = datetime.now(timezone.utc)
        ist_now = utc_now + timedelta(hours=5, minutes=30)

        if ist_now.weekday() >= 5: # Sat/Sun
            return False

        now_time = ist_now.time()
        start = datetime.strptime("09:15", "%H:%M").time()
        end = datetime.strptime("15:30", "%H:%M").time()
        return start <= now_time <= end
    except Exception:
        return True # Fail open if unsure

# Simple Client for Single Orders (avoiding httpx dependency)
class SimpleOrderClient:
    def __init__(self, api_key, host):
        self.api_key = api_key
        self.host = host.rstrip('/')
        self.session = requests.Session()

    def placesmartorder(self, symbol, action, exchange, product, quantity, pricetype="MARKET"):
        url = f"{self.host}/api/v1/placesmartorder"
        payload = {
            "apikey": self.api_key,
            "strategy": STRATEGY_NAME,
            "symbol": symbol,
            "action": action,
            "exchange": exchange,
            "pricetype": pricetype,
            "product": product,
            "quantity": quantity,
            "position_size": quantity # simple 1:1 mapping
        }
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Order Error: {e}", flush=True)
            return {"status": "error", "message": str(e)}


class SensexOIMomentumStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.order_client = SimpleOrderClient(api_key=API_KEY, host=HOST)

        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.debouncer = SignalDebouncer()

        self.expiry = EXPIRY_DATE if EXPIRY_DATE else None
        self.last_expiry_check = 0
        self.entered_today = False # Note: This strategy allows multiple trades per day if conditions met

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")
        self.logger.info(format_kv(
            underlying=UNDERLYING,
            pcr_bull=PCR_BULLISH,
            pcr_bear=PCR_BEARISH,
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            wall_prox=WALL_PROXIMITY_PTS
        ))

    def ensure_expiry(self):
        """Refreshes expiry date if needed."""
        if EXPIRY_DATE:
            self.expiry = EXPIRY_DATE
            return

        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > EXPIRY_REFRESH_SEC):
            try:
                res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
                if res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        self.expiry = choose_nearest_expiry(dates)
                        self.last_expiry_check = now
                        self.logger.info(f"Selected Expiry: {self.expiry}")
                    else:
                        self.logger.warning("No expiry dates found.")
                else:
                    self.logger.warning(f"Expiry fetch failed: {res.get('message')}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def is_time_window_open(self):
        """Checks if current time is within entry window."""
        utc_now = datetime.now(timezone.utc)
        ist_now = utc_now + timedelta(hours=5, minutes=30)
        now_time = ist_now.time()

        try:
            start = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
            end = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()
            return start <= now_time <= end
        except ValueError:
            self.logger.error("Invalid time format in configuration")
            return False

    def is_expiry_day(self):
        """Checks if today matches the expiry date."""
        if not self.expiry:
            return False
        try:
            # Format: DDMMMYY e.g. 14FEB26
            expiry_dt = datetime.strptime(self.expiry, "%d%b%y").date()
            utc_now = datetime.now(timezone.utc)
            today = (utc_now + timedelta(hours=5, minutes=30)).date()
            return today == expiry_dt
        except ValueError:
            return False

    def should_terminate(self):
        """Checks if strategy should terminate for the day."""
        utc_now = datetime.now(timezone.utc)
        ist_now = utc_now + timedelta(hours=5, minutes=30)
        now_time = ist_now.time()

        try:
            # Check Friday specific exit time
            if self.is_expiry_day():
                exit_time = datetime.strptime(FRIDAY_EXIT_TIME, "%H:%M").time()
                if now_time >= exit_time:
                    return True, "Friday Expiry Auto-Exit"

            # Normal daily exit time
            exit_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
            if now_time >= exit_time:
                return True, "EOD Auto-Squareoff"

            return False, ""
        except ValueError:
            return False, ""

    def calculate_pcr_and_walls(self, chain):
        """Calculates PCR and identifies OI walls (max OI strikes)."""
        total_ce_oi = 0
        total_pe_oi = 0
        max_ce_oi = -1
        max_pe_oi = -1
        call_wall_strike = None
        put_wall_strike = None

        for item in chain:
            ce_oi = safe_int(item.get("ce", {}).get("oi", 0))
            pe_oi = safe_int(item.get("pe", {}).get("oi", 0))

            total_ce_oi += ce_oi
            total_pe_oi += pe_oi

            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                call_wall_strike = item["strike"]

            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                put_wall_strike = item["strike"]

        pcr = (total_pe_oi / total_ce_oi) if total_ce_oi > 0 else 0.0
        return pcr, call_wall_strike, put_wall_strike

    def get_atm_strike(self, chain):
        """Finds ATM strike from chain data."""
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return item["strike"]
        return None

    def get_option_details(self, chain, strike, option_type):
        """Resolves symbol and LTP for a specific strike."""
        for item in chain:
            if item["strike"] == strike:
                opt = item.get(option_type.lower(), {})
                return {
                    "symbol": opt.get("symbol"),
                    "ltp": safe_float(opt.get("ltp", 0)),
                    "quantity": QUANTITY,
                    "product": PRODUCT,
                    "option_type": option_type,
                    "strike": strike
                }
        return None

    def _close_position(self, chain, reason):
        """Closes all open positions."""
        self.logger.info(f"Closing position. Reason: {reason}")

        if not self.tracker.open_legs:
            return

        for leg in self.tracker.open_legs:
            # We are Long in this strategy (Buy CE or Buy PE)
            # So exit is always SELL
            exit_action = "SELL"

            self.logger.info(f"Executing Exit: {exit_action} {leg['symbol']}")
            try:
                resp = self.order_client.placesmartorder(
                    symbol=leg["symbol"],
                    action=exit_action,
                    exchange=OPTIONS_EXCHANGE,
                    product=leg["product"],
                    quantity=leg["quantity"]
                )
                self.logger.info(f"Order Resp: {resp}")
                time.sleep(0.5)
            except Exception as e:
                self.logger.error(f"Failed to close leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.logger.info("Tracker cleared.")

    def _open_position(self, chain, option_type, entry_reason):
        """Places a single-leg directional order."""
        atm_strike = self.get_atm_strike(chain)
        if not atm_strike:
            self.logger.warning("ATM strike not found.")
            return

        details = self.get_option_details(chain, atm_strike, option_type)
        if not details or not details["symbol"]:
            self.logger.warning(f"Could not resolve ATM {option_type} details.")
            return

        action = "BUY" # Directional Momentum

        try:
            self.logger.info(f"Placing {action} order for {details['symbol']} ({entry_reason})")
            resp = self.order_client.placesmartorder(
                symbol=details["symbol"],
                action=action,
                exchange=OPTIONS_EXCHANGE,
                product=PRODUCT,
                quantity=QUANTITY,
                pricetype="MARKET"
            )

            if resp.get("status") == "success":
                self.logger.info(f"Order Success: {resp}")
                self.limiter.record()

                # Add to tracker
                # For BUY strategy, side="BUY" (Debit)
                # Tracker needs list of legs
                leg_for_tracker = details.copy()
                leg_for_tracker["action"] = action

                self.tracker.add_legs(
                    legs=[leg_for_tracker],
                    entry_prices=[details["ltp"]],
                    side="BUY"
                )
                self.logger.info(f"Position tracked. Reason: {entry_reason}")
            else:
                self.logger.error(f"Order Failed: {resp.get('message')}")

        except Exception as e:
            self.logger.error(f"Order Execution Error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # Check Market Open
                if not is_market_open_local():
                    if datetime.now(timezone.utc).hour < 3:
                        self.entered_today = False # Reset for new day logic (if needed)

                    self.logger.debug("Market is closed.")
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No expiry available.")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # Fetch Chain
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT,
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10) # Need more strikes for walls
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # 1. EXIT MANAGEMENT
                should_term, term_reason = self.should_terminate()

                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if should_term:
                        exit_now = True
                        exit_reason = term_reason

                    if exit_now:
                        self.logger.info(f"Exit signal: {exit_reason}")
                        self._close_position(chain, exit_reason)
                        if should_term:
                             self.logger.info("Terminated for the day. Sleeping.")
                             time.sleep(SLEEP_SECONDS * 2)
                        continue

                # 2. CALCULATE INDICATORS
                pcr, call_wall, put_wall = self.calculate_pcr_and_walls(chain)

                # Proximity Checks
                near_call_wall = False
                near_put_wall = False

                if call_wall:
                    dist_call = abs(call_wall - underlying_ltp)
                    near_call_wall = dist_call <= WALL_PROXIMITY_PTS

                if put_wall:
                    dist_put = abs(put_wall - underlying_ltp)
                    near_put_wall = dist_put <= WALL_PROXIMITY_PTS

                # 3. LOG STATUS
                self.logger.info(format_kv(
                    spot=f"{underlying_ltp:.2f}",
                    pcr=f"{pcr:.2f}",
                    walls=f"P:{put_wall}/C:{call_wall}",
                    prox=f"{'NearCall' if near_call_wall else ''}{'NearPut' if near_put_wall else ''}",
                    pos="OPEN" if self.tracker.open_legs else "FLAT"
                ))

                # 4. ENTRY LOGIC
                if self.tracker.open_legs:
                    time.sleep(SLEEP_SECONDS)
                    continue

                if should_term:
                    time.sleep(SLEEP_SECONDS)
                    continue

                if self.limiter.allow() and self.is_time_window_open():
                    # BULLISH: PCR > 1.2 (Oversold/Support) AND Near Put Wall (Support Bounce)
                    if pcr >= PCR_BULLISH and near_put_wall:
                        if self.debouncer.edge("bullish_entry", True):
                            self._open_position(chain, "CE", f"Bullish PCR:{pcr:.2f} + PutWall:{put_wall}")

                    # BEARISH: PCR < 0.8 (Overbought/Resistance) AND Near Call Wall (Resistance Reject)
                    elif pcr <= PCR_BEARISH and near_call_wall:
                        if self.debouncer.edge("bearish_entry", True):
                            self._open_position(chain, "PE", f"Bearish PCR:{pcr:.2f} + CallWall:{call_wall}")

            except KeyboardInterrupt:
                self.logger.info("Strategy stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    Strategy = SensexOIMomentumStrategy()
    try:
        Strategy.run()
    except Exception as e:
        print(f"Critical Error: {e}")
