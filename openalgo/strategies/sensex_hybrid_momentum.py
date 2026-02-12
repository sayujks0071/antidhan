#!/usr/bin/env python3
"""
SENSEX Hybrid Momentum & PCR Scalper (OpenAlgo Web UI Compatible)
Directional trading strategy based on Put-Call Ratio (PCR) and OI Wall Rejection.

Exchange: BFO (BSE F&O)
Underlying: SENSEX on BSE_INDEX
Expiry: Weekly Friday
Edge: Trades bounces off high OI walls when PCR confirms sentiment.
      - Bullish: PCR > 1.2 + Spot near Max Put OI (Support) -> Buy ATM CE
      - Bearish: PCR < 0.8 + Spot near Max Call OI (Resistance) -> Buy ATM PE
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone, time as time_obj

# Line-buffered output (required for real-time log capture)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
# sys.path.insert(0, utils_dir) # Avoid adding openalgo/utils as it shadows standard logging
# Also add local strategies/utils if present (where we put our files)
sys.path.insert(0, os.path.join(script_dir, "utils"))

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
# CONFIGURATION - SENSEX MOMENTUM SCALPER
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "sensex_hybrid_momentum")
UNDERLYING = os.getenv("UNDERLYING", "SENSEX")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "BSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "BFO")
PRODUCT = os.getenv("PRODUCT", "MIS")           # MIS=Intraday
QUANTITY = int(os.getenv("QUANTITY", "1"))        # 1 lot = 10 units for SENSEX
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "15")) # Wider view for OI Walls

# Strategy Thresholds
PCR_BULLISH = float(os.getenv("PCR_BULLISH", "1.2"))
PCR_BEARISH = float(os.getenv("PCR_BEARISH", "0.8"))
WALL_BOUNCE_BUFFER = float(os.getenv("WALL_BOUNCE_BUFFER", "150.0")) # Points from OI Wall to consider "near"

# Time Config
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:45") # Let market settle
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")
FRIDAY_EXIT_TIME = os.getenv("FRIDAY_EXIT_TIME", "14:30")

# Risk parameters (Aggressive Scalping)
SL_PCT = float(os.getenv("SL_PCT", "25"))        # % of entry premium
TP_PCT = float(os.getenv("TP_PCT", "60"))         # % of entry premium
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "20")) # Short hold time

# Rate limiting
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "90"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "15")) # Faster updates
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "5"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

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


class SensexHybridMomentumStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

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
        self.entered_today = False # Not strictly used if allowing multi-trades, relies on limiter

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")
        self.logger.info(format_kv(
            underlying=UNDERLYING,
            exchange=OPTIONS_EXCHANGE,
            pcr_bull=PCR_BULLISH,
            pcr_bear=PCR_BEARISH,
            wall_buffer=WALL_BOUNCE_BUFFER
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

    def is_market_open_local(self):
        """Checks if market is open (9:15 - 15:30 IST) using local time fallback."""
        try:
            # IST = UTC + 5:30
            utc_now = datetime.now(timezone.utc)
            ist_now = utc_now + timedelta(hours=5, minutes=30)

            if ist_now.weekday() >= 5: # Sat=5, Sun=6
                return False

            now_time = ist_now.time()
            start = time_obj(9, 15)
            end = time_obj(15, 30)
            return start <= now_time <= end
        except Exception:
            return True

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
            if self.is_expiry_day():
                exit_time = datetime.strptime(FRIDAY_EXIT_TIME, "%H:%M").time()
                if now_time >= exit_time:
                    return True, "Friday Expiry Auto-Exit"

            exit_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
            if now_time >= exit_time:
                return True, "EOD Auto-Squareoff"

            return False, ""
        except ValueError:
            return False, ""

    def get_atm_strike(self, chain):
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return item["strike"]
        return None

    def calculate_pcr(self, chain):
        call_oi = sum(safe_int((item.get("ce") or {}).get("oi")) for item in chain)
        put_oi = sum(safe_int((item.get("pe") or {}).get("oi")) for item in chain)
        return (put_oi / call_oi) if call_oi > 0 else 0.0

    def find_oi_walls(self, chain):
        max_call_oi = 0
        call_wall_strike = 0
        max_put_oi = 0
        put_wall_strike = 0

        for item in chain:
            strike = item["strike"]
            c_oi = safe_int((item.get("ce") or {}).get("oi"))
            p_oi = safe_int((item.get("pe") or {}).get("oi"))

            if c_oi > max_call_oi:
                max_call_oi = c_oi
                call_wall_strike = strike

            if p_oi > max_put_oi:
                max_put_oi = p_oi
                put_wall_strike = strike

        return call_wall_strike, put_wall_strike, max_call_oi, max_put_oi

    def _close_position(self, chain, reason):
        """Closes all open positions."""
        self.logger.info(f"Closing position. Reason: {reason}")
        if not self.tracker.open_legs:
            return

        exit_legs = []
        for leg in self.tracker.open_legs:
            original_action = leg.get("action", "BUY")
            exit_action = "BUY" if original_action == "SELL" else "SELL" # Usually SELL to close long

            exit_legs.append({
                "symbol": leg["symbol"],
                "option_type": leg.get("option_type", "CE"),
                "action": exit_action,
                "quantity": leg["quantity"],
                "product": PRODUCT,
                "offset": leg.get("offset", "ATM")
            })

        try:
            response = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=UNDERLYING_EXCHANGE,
                expiry_date=self.expiry,
                legs=exit_legs
            )
            self.logger.info(f"Exit Order Response: {response}")
        except Exception as e:
            self.logger.error(f"Exit failed: {e}")

        self.tracker.clear()
        self.logger.info("Tracker cleared.")

    def _open_position(self, chain, option_type, reason):
        """Places Directional Buy Order."""
        # Buy ATM Option
        offset = "ATM"
        action = "BUY" # Buying for momentum/scalp

        target_leg = None
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset:
                target_leg = {
                    "symbol": opt.get("symbol"),
                    "ltp": safe_float(opt.get("ltp", 0)),
                    "quantity": QUANTITY,
                    "product": PRODUCT,
                    "option_type": option_type,
                    "offset": offset,
                    "action": action
                }
                break

        if not target_leg:
            self.logger.warning(f"Could not find ATM {option_type}")
            return

        api_legs = [{
            "offset": offset,
            "option_type": option_type,
            "action": action,
            "quantity": QUANTITY,
            "product": PRODUCT
        }]

        try:
            response = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=UNDERLYING_EXCHANGE,
                expiry_date=self.expiry,
                legs=api_legs
            )

            if response.get("status") == "success":
                self.logger.info(f"Order Success: {response}")
                self.limiter.record()

                self.tracker.add_legs(
                    legs=[target_leg],
                    entry_prices=[target_leg["ltp"]],
                    side="BUY" # Directional Long
                )
                self.logger.info(f"Position tracked. Reason: {reason}")
            else:
                self.logger.error(f"Order Failed: {response.get('message')}")

        except Exception as e:
            self.logger.error(f"Order Execution Error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                if not self.is_market_open_local():
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=STRIKE_COUNT)
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
                        self._close_position(chain, exit_reason)
                        if should_term:
                             self.logger.info("Terminated for the day.")
                             time.sleep(SLEEP_SECONDS * 4)
                        continue

                # 2. CALCULATE INDICATORS
                pcr = self.calculate_pcr(chain)
                call_wall, put_wall, max_c_oi, max_p_oi = self.find_oi_walls(chain)

                # Distance to walls
                dist_to_call_wall = call_wall - underlying_ltp
                dist_to_put_wall = underlying_ltp - put_wall

                # 3. LOG STATUS
                self.logger.info(format_kv(
                    spot=f"{underlying_ltp:.2f}",
                    pcr=f"{pcr:.2f}",
                    c_wall=call_wall,
                    p_wall=put_wall,
                    pos="OPEN" if self.tracker.open_legs else "FLAT"
                ))

                # 4. ENTRY LOGIC
                if self.tracker.open_legs or should_term:
                    time.sleep(SLEEP_SECONDS)
                    continue

                if self.limiter.allow() and self.is_time_window_open():

                    # Logic 1: Bullish Rebound (PCR Bullish + Spot near Put Wall Support)
                    bullish_signal = False
                    if pcr >= PCR_BULLISH:
                        if 0 < dist_to_put_wall <= WALL_BOUNCE_BUFFER:
                            bullish_signal = True

                    # Logic 2: Bearish Rejection (PCR Bearish + Spot near Call Wall Resistance)
                    bearish_signal = False
                    if pcr <= PCR_BEARISH:
                        if 0 < dist_to_call_wall <= WALL_BOUNCE_BUFFER:
                            bearish_signal = True

                    # Execute
                    if self.debouncer.edge("bull_entry", bullish_signal):
                        self.logger.info(f"Bullish Entry: PCR {pcr} + Support Bounce")
                        self._open_position(chain, "CE", "bullish_pcr_support")

                    elif self.debouncer.edge("bear_entry", bearish_signal):
                        self.logger.info(f"Bearish Entry: PCR {pcr} + Resistance Rejection")
                        self._open_position(chain, "PE", "bearish_pcr_resistance")

            except KeyboardInterrupt:
                self.logger.info("Strategy stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    Strategy = SensexHybridMomentumStrategy()
    try:
        Strategy.run()
    except Exception as e:
        print(f"Critical Error: {e}")
