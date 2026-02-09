#!/usr/bin/env python3
"""
[Sensex Iron Condor] - SENSEX Weekly Options (OpenAlgo Web UI Compatible)
Sells OTM2 strangles and buys OTM4 wings for defined-risk theta decay on SENSEX/BFO.

Exchange: BFO (BSE F&O)
Underlying: SENSEX on BSE_INDEX
Expiry: Weekly Friday
"""
import os
import sys
import time
from datetime import datetime

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
    from trading_utils import is_market_open, APIClient
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
        RiskConfig,
        RiskManager,
    )
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


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
EXIT_TIME_NORMAL = os.getenv("EXIT_TIME_NORMAL", "15:15")
EXIT_TIME_FRIDAY = os.getenv("EXIT_TIME_FRIDAY", "14:00")

# Risk parameters
SL_PCT = float(os.getenv("SL_PCT", "35.0"))        # % of entry premium
TP_PCT = float(os.getenv("TP_PCT", "45.0"))         # % of entry premium
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))

# Rate limiting
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "20"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "6"))

# Manual expiry override (format: 14FEB26)
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

# Defensive normalization: SENSEX/BANKEX trade on BSE
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and UNDERLYING_EXCHANGE.upper() == "NSE_INDEX":
    UNDERLYING_EXCHANGE = "BSE_INDEX"
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and OPTIONS_EXCHANGE.upper() == "NFO":
    OPTIONS_EXCHANGE = "BFO"


class SensexIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

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
        self.last_trade_date = None

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")
        self.logger.info(format_kv(
            sl=SL_PCT, tp=TP_PCT, max_hold=MAX_HOLD_MIN,
            qty=QUANTITY, min_prem=MIN_STRADDLE_PREMIUM
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
        now = datetime.now().time()
        try:
            start = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
            end = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()
            return start <= now <= end
        except ValueError:
            self.logger.error("Invalid time format in configuration")
            return False

    def check_exit_time(self):
        """Checks if it's time to force exit based on strategy rules."""
        now = datetime.now()
        is_friday = now.weekday() == 4  # Monday is 0, Sunday is 6

        exit_str = EXIT_TIME_FRIDAY if is_friday else EXIT_TIME_NORMAL
        try:
            exit_time = datetime.strptime(exit_str, "%H:%M").time()
            return now.time() >= exit_time
        except ValueError:
            return False

    def get_atm_strike(self, chain):
        """Finds ATM strike from chain data."""
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return item["strike"]
        # Fallback using spot price if available
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
                    "product": PRODUCT
                }
        return None

    def _close_position(self, chain, reason):
        """Closes all open positions."""
        self.logger.info(f"Closing position. Reason: {reason}")

        exit_legs = []
        for leg in self.tracker.open_legs:
            # Reverse action
            action = "BUY" if leg.get("action") == "SELL" else "SELL"
            exit_legs.append({
                "symbol": leg["symbol"],
                "action": action,
                "quantity": leg["quantity"],
                "product": PRODUCT,
                "pricetype": "MARKET"
            })

        if not exit_legs:
            self.logger.warning("No open legs to close, but close requested.")
            self.tracker.clear()
            return

        for leg in exit_legs:
            try:
                res = self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=leg["symbol"],
                    action=leg["action"],
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=leg["product"],
                    quantity=leg["quantity"],
                    position_size=leg["quantity"]
                )
                self.logger.info(f"Exit Order: {leg['symbol']} {leg['action']} -> {res}")
            except Exception as e:
                self.logger.error(f"Exit failed for {leg['symbol']}: {e}")

        self.tracker.clear()
        self.logger.info("Position closed and tracker cleared.")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # Reset daily flag if new day
                today = datetime.now().date()
                if self.last_trade_date != today:
                    self.entered_today = False
                    self.last_trade_date = today

                if not is_market_open():
                    self.logger.debug("Market is closed. Sleeping...")
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No expiry available.")
                    time.sleep(SLEEP_SECONDS)
                    continue

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

                # 1. EXIT MANAGEMENT (always check exits BEFORE entries)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # Force exit check (Time/Friday)
                    if not exit_now and self.check_exit_time():
                        exit_now = True
                        exit_reason = "time_stop_eod"

                    if exit_now:
                        self.logger.info(f"Exit signal: {exit_reason}")
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # 2. LOG STATUS
                atm_strike = self.get_atm_strike(chain)
                straddle_prem = self.calculate_straddle_premium(chain, atm_strike) if atm_strike else 0

                self.logger.info(format_kv(
                    spot=f"{underlying_ltp:.2f}",
                    straddle=f"{straddle_prem:.2f}",
                    pos="OPEN" if self.tracker.open_legs else "FLAT",
                    expiry=self.expiry or "N/A",
                ))

                # 3. SKIP if already in position or already entered today (and limiter forbids)
                # Note: entered_today logic can be strict or loose. Here we rely on TradeLimiter mostly.
                if self.tracker.open_legs:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 4. ENTRY LOGIC
                if self.is_time_window_open():

                    if not self.limiter.allow():
                        self.logger.debug("Trade limiter active. Skipping entry.")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    if straddle_prem < MIN_STRADDLE_PREMIUM:
                        self.logger.debug(f"Premium {straddle_prem} < {MIN_STRADDLE_PREMIUM}. Waiting.")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    # Entry Signal: Simple valid conditions for now (can add indicators here)
                    # Iron Condor: Sell OTM2, Buy OTM4
                    # Removed debouncer as requested to allow multiple trades/retries
                    # Logic is now gate-based: open_legs=False AND limiter.allow()=True

                    self.logger.info("Entry signal detected. Placing Iron Condor orders...")

                    definitions = [
                        ("OTM4", "CE", "BUY"),
                        ("OTM4", "PE", "BUY"),
                        ("OTM2", "CE", "SELL"),
                        ("OTM2", "PE", "SELL")
                    ]

                    tracking_legs = []
                    entry_prices = []
                    valid_setup = True

                    for offset, otype, action in definitions:
                        details = self.get_leg_details(chain, offset, otype)
                        if details:
                            details["action"] = action
                            tracking_legs.append(details)
                            entry_prices.append(details["ltp"])
                        else:
                            self.logger.warning(f"Could not resolve leg: {offset} {otype}")
                            valid_setup = False
                            break

                    if valid_setup:
                        api_legs = []
                        for offset, otype, action in definitions:
                            api_legs.append({
                                "offset": offset,
                                "option_type": otype,
                                "action": action,
                                "quantity": QUANTITY,
                                "product": PRODUCT
                            })

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
                                self.entered_today = True

                                self.tracker.add_legs(
                                    legs=tracking_legs,
                                    entry_prices=entry_prices,
                                    side="SELL"
                                )
                                self.logger.info("Iron Condor positions tracked.")
                            else:
                                self.logger.error(f"Order Failed: {response.get('message')}")

                        except Exception as e:
                            self.logger.error(f"Order Execution Error: {e}")
                    else:
                        self.logger.warning("Setup invalid (missing strikes). Skipping.")

            except Exception as e:
                self.logger.error(f"Error: {e}")
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    Strategy = SensexIronCondorStrategy
    Strategy().run()
