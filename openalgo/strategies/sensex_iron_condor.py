#!/usr/bin/env python3
"""
SENSEX Weekly Options Strategy (OpenAlgo Web UI Compatible)
Iron Condor: Sells OTM2 CE/PE and Buys OTM4 CE/PE (Wings) for defined-risk theta decay.

Exchange: BFO (BSE F&O)
Underlying: SENSEX on BSE_INDEX
Expiry: Weekly Friday
Edge: Theta decay + defined risk via wings, exploiting lower STT and 100-pt strikes on BSE.
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
# Note: Corrected to point to strategies/utils to avoid openalgo/utils (logging shadow)
utils_dir = os.path.join(script_dir, "utils")
sys.path.insert(0, utils_dir)

try:
    from trading_utils import is_market_open
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        normalize_expiry,
        safe_float,
        safe_int,
    )
    from strategy_common import (
        SignalDebouncer,
        TradeLedger,
        TradeLimiter,
        format_kv,
        DataFreshnessGuard,
        RiskConfig,
        RiskManager,
    )
except ImportError:
    # We continue even if import fails, as we might use local fallbacks
    print("WARNING: strategy utilities import failed. Using local fallbacks where possible.", flush=True)
    # sys.exit(1) # We try to proceed with local fallbacks if critical

# Local Fallback for is_market_open
def is_market_open_local():
    """Checks if market is open (9:15 - 15:30 IST)."""
    try:
        utc_now = datetime.now(timezone.utc)
        ist_now = utc_now + timedelta(hours=5, minutes=30)
        if ist_now.weekday() >= 5: return False
        now_time = ist_now.time()
        start = datetime.strptime("09:15", "%H:%M").time()
        end = datetime.strptime("15:30", "%H:%M").time()
        return start <= now_time <= end
    except:
        return True

class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)

# ===========================
# API KEY RETRIEVAL
# ===========================
API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

# Attempt to load from DB if env var missing (Platform specific)
root_dir = os.path.dirname(script_dir) # openalgo/
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
# CONFIGURATION - SENSEX WEEKLY OPTIONS
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "sensex_iron_condor")
UNDERLYING = os.getenv("UNDERLYING", "SENSEX")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "BSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "BFO")
PRODUCT = os.getenv("PRODUCT", "MIS")           # MIS=Intraday, NRML=Positional
QUANTITY = int(os.getenv("QUANTITY", "1"))        # 1 lot = 10 units for SENSEX
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "12"))

# Strategy-specific parameters
MIN_STRADDLE_PREMIUM = float(os.getenv("MIN_STRADDLE_PREMIUM", "400.0"))
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "10:00")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")
FRIDAY_EXIT_TIME = os.getenv("FRIDAY_EXIT_TIME", "14:00") # Early exit on expiry day

# Risk parameters
SL_PCT = float(os.getenv("SL_PCT", "35"))        # % of entry premium
TP_PCT = float(os.getenv("TP_PCT", "45"))         # % of entry premium
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))

# Rate limiting
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Manual expiry override (format: 14FEB26)
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

# Defensive normalization: SENSEX/BANKEX trade on BSE
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and UNDERLYING_EXCHANGE.upper() == "NSE_INDEX":
    UNDERLYING_EXCHANGE = "BSE_INDEX"
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and OPTIONS_EXCHANGE.upper() == "NFO":
    OPTIONS_EXCHANGE = "BFO"

class SensexWeeklyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Use provided tracker
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
        self.entered_today = False

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")
        self.logger.info(format_kv(
            underlying=UNDERLYING,
            exchange=OPTIONS_EXCHANGE,
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold=MAX_HOLD_MIN,
            min_straddle=MIN_STRADDLE_PREMIUM
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
            return False

    def is_expiry_day(self):
        """Checks if today matches the expiry date."""
        if not self.expiry: return False
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

    def get_atm_strike(self, chain):
        """Finds ATM strike from chain data."""
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return item["strike"]
        return None

    def calculate_straddle_premium(self, chain, atm_strike):
        """Calculates combined premium of ATM CE and PE."""
        ce_ltp = 0.0
        pe_ltp = 0.0
        for item in chain:
            if item["strike"] == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                break
        return ce_ltp + pe_ltp

    def get_leg_details(self, chain, offset, option_type):
        """Helper to resolve symbol and LTP from chain based on offset."""
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset:
                return {
                    "symbol": opt.get("symbol"),
                    "ltp": safe_float(opt.get("ltp", 0)),
                    "quantity": QUANTITY,
                    "product": PRODUCT,
                    "option_type": option_type,
                    "offset": offset
                }
        return None

    def _close_position(self, chain, reason):
        """Closes all open positions using multi-order."""
        self.logger.info(f"Closing position. Reason: {reason}")

        if not self.tracker.open_legs:
            return

        exit_legs = []
        # Sort legs: BUY first (cover shorts), then SELL (close longs)
        # Original positions: Iron Condor = Short OTM2 (SELL), Long OTM4 (BUY)
        # To Close: Buy OTM2, Sell OTM4.
        # We want to perform BUY actions first.

        for leg in self.tracker.open_legs:
            original_action = leg.get("action")
            exit_action = "BUY" if original_action == "SELL" else "SELL"

            exit_legs.append({
                "offset": leg.get("offset", "ATM"),
                "option_type": leg.get("option_type", "CE"),
                "action": exit_action,
                "quantity": leg["quantity"],
                "product": PRODUCT
            })

        # Sort: BUY first
        exit_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

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

    def _open_position(self, chain, entry_reason):
        """Places Iron Condor orders."""
        # Iron Condor: Sell OTM2, Buy OTM4
        definitions = [
            ("OTM4", "CE", "BUY"),   # Wing
            ("OTM4", "PE", "BUY"),   # Wing
            ("OTM2", "CE", "SELL"),  # Body
            ("OTM2", "PE", "SELL")   # Body
        ]

        tracking_legs = []
        entry_prices = []
        api_legs = []
        valid_setup = True

        for offset, otype, action in definitions:
            details = self.get_leg_details(chain, offset, otype)
            if details:
                details["action"] = action
                tracking_legs.append(details)
                entry_prices.append(details["ltp"])

                api_legs.append({
                    "offset": offset,
                    "option_type": otype,
                    "action": action,
                    "quantity": QUANTITY,
                    "product": PRODUCT
                })
            else:
                self.logger.warning(f"Could not resolve leg: {offset} {otype}")
                valid_setup = False
                break

        if valid_setup:
            try:
                # Buy legs execute first automatically by backend/broker usually,
                # but we send list. OpenAlgo usually handles order.
                # If we want to be safe, we order BUYs first in the list (which we did).

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
                    self.entered_today = True

                    self.tracker.add_legs(
                        legs=tracking_legs,
                        entry_prices=entry_prices,
                        side="SELL" # Net Credit Strategy
                    )
                    self.logger.info(f"Position tracked. Reason: {entry_reason}")
                else:
                    self.logger.error(f"Order Failed: {response.get('message')}")

            except Exception as e:
                self.logger.error(f"Order Execution Error: {e}")
        else:
            self.logger.warning("Setup invalid (missing strikes). Skipping.")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # Check Market Open
                try:
                    market_open = is_market_open()
                except NameError:
                    market_open = is_market_open_local()

                if not market_open:
                    # Reset daily flag if early morning
                    if datetime.now(timezone.utc).hour < 3:
                        self.entered_today = False

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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
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
                atm_strike = self.get_atm_strike(chain)
                straddle_premium = 0
                if atm_strike:
                    straddle_premium = self.calculate_straddle_premium(chain, atm_strike)

                # 3. LOG STATUS
                self.logger.info(format_kv(
                    spot=f"{underlying_ltp:.2f}",
                    straddle=f"{straddle_premium:.2f}",
                    pos="OPEN" if self.tracker.open_legs else "FLAT",
                    expiry=self.expiry or "N/A",
                    entered=self.entered_today
                ))

                # 4. ENTRY LOGIC
                if self.tracker.open_legs:
                    time.sleep(SLEEP_SECONDS)
                    continue

                if should_term:
                    time.sleep(SLEEP_SECONDS)
                    continue

                if self.limiter.allow() and self.is_time_window_open() and not self.entered_today:

                    # Entry Conditions:
                    # 1. Straddle Premium > MIN_STRADDLE_PREMIUM
                    # 2. Debounced signal

                    condition = straddle_premium >= MIN_STRADDLE_PREMIUM

                    if self.debouncer.edge("entry_signal", condition):
                         if condition: # Double check
                            self.logger.info(f"Entry Signal: Straddle {straddle_premium} >= {MIN_STRADDLE_PREMIUM}")
                            self._open_position(chain, "premium_selling_opportunity")
                    else:
                        if condition:
                             self.logger.debug("Signal debounced (already triggered).")

            except KeyboardInterrupt:
                self.logger.info("Strategy stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    Strategy = SensexWeeklyIronCondor()
    try:
        Strategy.run()
    except Exception as e:
        print(f"Critical Error: {e}")
