#!/usr/bin/env python3
"""
[Nifty Smart Momentum] - NIFTY Options (OpenAlgo Web UI Compatible)
Momentum Strategy using PCR and OI Walls.
Logic:
- Entry: PCR > 1.25 (Bullish) or PCR < 0.75 (Bearish).
- Filter: Avoid buying Call near Resistance (Call Wall) or Put near Support (Put Wall).
- Risk: SL 25% | TP 50% | Max Hold 30 min.
"""
import os
import sys
import time
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
        normalize_expiry,
        safe_float,
        safe_int,
    )
    from strategy_common import SignalDebouncer, TradeLedger, TradeLimiter, format_kv
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)

# Robust Market Open Check (Local Fallback to avoid dependencies)
try:
    from trading_utils import is_market_open
except ImportError:
    print("Warning: trading_utils import failed. Using local is_market_open fallback.", flush=True)
    def is_market_open():
        """Check if market is open (09:15 - 15:30 IST)."""
        # IST is UTC+5:30
        ist_offset = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist_offset)

        # Check weekend (5=Saturday, 6=Sunday)
        if now.weekday() >= 5:
            return False

        current_time = now.time()
        start_time = datetime.strptime("09:15", "%H:%M").time()
        end_time = datetime.strptime("15:30", "%H:%M").time()

        return start_time <= current_time <= end_time


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# API Key retrieval
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


# ===========================
# CONFIGURATION
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftySmartMomentum")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Strategy Parameters
PCR_BULLISH = safe_float(os.getenv("PCR_BULLISH", "1.25"))
PCR_BEARISH = safe_float(os.getenv("PCR_BEARISH", "0.75"))
OI_WALL_BUFFER = safe_int(os.getenv("OI_WALL_BUFFER", "50"))  # Points away from wall to avoid entry

# Risk Parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "25.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "30"))

# Rate Limiting
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "10"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "3"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

# Manual Expiry Override
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()


class NiftySmartMomentumStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.expiry = EXPIRY_DATE
        self.last_expiry_check = 0
        self.entered_today = False # Not strictly used if limiter handles daily count, but good for single-shot logic if needed
        self.current_date = datetime.now().date()

    def ensure_expiry(self):
        """Refresh expiry date if needed."""
        if self.expiry and (time.time() - self.last_expiry_check < EXPIRY_REFRESH_SEC):
            return

        # If manually set, don't override unless empty
        if os.getenv("EXPIRY_DATE"):
            self.expiry = os.getenv("EXPIRY_DATE")
            return

        self.logger.info("Fetching available expiry dates...")
        try:
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.last_expiry_check = time.time()
                    self.logger.info(f"Selected expiry: {self.expiry}")
                else:
                    self.logger.warning("No valid future expiry found.")
            else:
                self.logger.error(f"Failed to fetch expiry: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Expiry fetch error: {e}")

    def calculate_indicators(self, chain, spot_price):
        """Calculate PCR and identify OI Walls."""
        total_ce_oi = 0
        total_pe_oi = 0
        max_ce_oi = 0
        max_pe_oi = 0
        max_ce_oi_strike = 0
        max_pe_oi_strike = 0

        for item in chain:
            strike = item["strike"]
            ce = item.get("ce", {})
            pe = item.get("pe", {})

            ce_oi = safe_int(ce.get("oi", 0))
            pe_oi = safe_int(pe.get("oi", 0))

            total_ce_oi += ce_oi
            total_pe_oi += pe_oi

            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                max_ce_oi_strike = strike

            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                max_pe_oi_strike = strike

        pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0.0

        return {
            "pcr": pcr,
            "max_ce_oi_strike": max_ce_oi_strike,
            "max_pe_oi_strike": max_pe_oi_strike
        }

    def _close_position(self, chain, reason):
        """Close all open legs."""
        self.logger.info(f"Closing position. Reason: {reason}")

        if not self.tracker.open_legs:
            return

        # Prepare exit legs (Reverse actions)
        legs_to_close = []
        for leg in self.tracker.open_legs:
            close_leg = {
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": "BUY" if leg["action"] == "SELL" else "SELL", # Reverse
                "quantity": leg["quantity"],
                "product": leg.get("product", PRODUCT)
            }
            legs_to_close.append(close_leg)

        # Sort: BUY actions first (if any)
        legs_to_close.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=legs_to_close
            )
            self.logger.info(f"Exit Order Response: {res}")

            if res.get("status") == "success":
                self.tracker.clear()
            else:
                self.logger.error(f"Exit failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _open_position(self, chain, side, reason):
        """Open Long Call or Long Put Position."""
        self.logger.info(f"Attempting to open {side} Position ({reason})...")

        # Find ATM strike
        atm_strike = None
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                atm_strike = item["strike"]
                break

        if not atm_strike:
            self.logger.warning("Could not find ATM strike.")
            return

        # Define leg: Buy ATM Call or Put
        option_type = "CE" if side == "LONG_CALL" else "PE"

        # Find the specific option symbol
        target_option = None
        for item in chain:
            if item["strike"] == atm_strike:
                target_option = item.get(option_type.lower(), {})
                break

        if not target_option:
            self.logger.warning(f"Could not find ATM {option_type}")
            return

        symbol = target_option.get("symbol")
        ltp = safe_float(target_option.get("ltp"))

        if not symbol or ltp <= 0:
            self.logger.warning(f"Invalid symbol or LTP for {option_type}")
            return

        api_legs = [{
            "symbol": symbol,
            "option_type": option_type,
            "action": "BUY",
            "quantity": QUANTITY,
            "product": PRODUCT
        }]

        resolved_legs = [{
            "symbol": symbol,
            "option_type": option_type,
            "action": "BUY",
            "quantity": QUANTITY,
            "entry_price": ltp,
            "product": PRODUCT
        }]

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=api_legs
            )

            if res.get("status") == "success":
                self.logger.info(f"Entry Order Success: {res}")

                # Add to Tracker
                entry_prices = [leg["entry_price"] for leg in resolved_legs]
                self.tracker.add_legs(resolved_legs, entry_prices, side="BUY")

                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING}")

        while True:
            try:
                # 0. Daily Reset Check (if needed)
                if datetime.now().date() != self.current_date:
                    self.current_date = datetime.now().date()
                    # self.limiter auto-resets daily

                # 1. Market Hours Check
                if not is_market_open():
                    time.sleep(60)
                    continue

                # 2. Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No expiry available.")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch Data
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

                # 4. Exit Management (Priority)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Exit (3:15 PM)
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    eod_time = datetime.strptime("15:15", "%H:%M").time()

                    if now.time() >= eod_time:
                        exit_now = True
                        exit_reason = "eod_sqoff"

                    if exit_now:
                        self.logger.info(f"Exit Signal: {exit_reason}")
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue
                    else:
                         self.logger.info(format_kv(
                            spot=f"{underlying_ltp:.2f}",
                            pos="OPEN",
                            pnl_check="running"
                        ))

                # 5. Entry Logic
                if not self.tracker.open_legs:
                    # Calculate Indicators
                    indicators = self.calculate_indicators(chain, underlying_ltp)
                    pcr = indicators["pcr"]
                    max_ce_strike = indicators["max_ce_oi_strike"]
                    max_pe_strike = indicators["max_pe_oi_strike"]

                    self.logger.info(format_kv(
                        spot=f"{underlying_ltp:.2f}",
                        pcr=f"{pcr:.2f}",
                        res=max_ce_strike,
                        sup=max_pe_strike
                    ))

                    # Logic Definition
                    # Bullish: PCR > Threshold AND Not near Resistance
                    is_bullish = pcr > PCR_BULLISH
                    not_near_resistance = underlying_ltp < (max_ce_strike - OI_WALL_BUFFER)

                    # Bearish: PCR < Threshold AND Not near Support
                    is_bearish = pcr < PCR_BEARISH
                    not_near_support = underlying_ltp > (max_pe_strike + OI_WALL_BUFFER)

                    # Debounce Signals
                    # Note: We must call edge() every loop iteration for state tracking
                    entry_long = self.debouncer.edge("long_signal", is_bullish and not_near_resistance)
                    entry_short = self.debouncer.edge("short_signal", is_bearish and not_near_support)

                    if self.limiter.allow():
                        if entry_long:
                            self._open_position(chain, "LONG_CALL", f"pcr_{pcr:.2f}_bullish")
                        elif entry_short:
                            self._open_position(chain, "LONG_PUT", f"pcr_{pcr:.2f}_bearish")

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftySmartMomentumStrategy()
    strategy.run()
