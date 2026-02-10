#!/usr/bin/env python3
"""
NiftyDynamicIronCondor - NIFTY Options (OpenAlgo Web UI Compatible)
Sells OTM2 Strangles with OTM5 Protection (Iron Condor) for defined-risk theta decay.
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
utils_dir = os.path.join(script_dir, "utils")
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
    from strategy_common import SignalDebouncer, TradeLedger, TradeLimiter, format_kv
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# ===========================
# CONFIGURATION
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyDynamicIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Strategy Parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "40.0"))    # Stop Loss % on Premium
TP_PCT = safe_float(os.getenv("TP_PCT", "60.0"))    # Take Profit % on Premium
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))
MIN_PREMIUM = safe_float(os.getenv("MIN_PREMIUM", "100.0"))

# Time Filters
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:30")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")

# Rate Limiting
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Manual Expiry Override (DDMMMYY)
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()


# API Key Retrieval
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


class NiftyDynamicIronCondorStrategy:
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

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")
        self.logger.info(format_kv(
            underlying=UNDERLYING,
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold=MAX_HOLD_MIN
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

    def should_terminate(self):
        """Checks if strategy should terminate for the day (after EXIT_TIME)."""
        now = datetime.now().time()
        try:
            exit_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
            return now >= exit_time
        except ValueError:
            return False

    def get_atm_strike(self, chain):
        """Finds ATM strike from chain data."""
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return item["strike"]
        # Fallback: find closest to underlying_ltp if passed, but here we iterate labels
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
            entry_action = leg.get("action")
            exit_action = "BUY" if entry_action == "SELL" else "SELL"

            exit_legs.append({
                "symbol": leg["symbol"],
                "action": exit_action,
                "quantity": leg["quantity"],
                "product": PRODUCT,
                "pricetype": "MARKET"
            })

        if not exit_legs:
            self.logger.warning("No open legs to close.")
            self.tracker.clear()
            return

        # Execute exit orders individually (or use multiorder if supported for closing, but placesmartorder is safer for individual legs)
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
        self.logger.info("Starting Strategy Loop...")

        while True:
            try:
                # Daily Reset Logic (Simple)
                if not is_market_open():
                    self.logger.debug("Market is closed. Sleeping...")
                    # If it's early morning, reset entered_today
                    if datetime.now().hour < 9:
                        self.entered_today = False
                    time.sleep(SLEEP_SECONDS)
                    continue

                # Ensure Expiry
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # Fetch Option Chain
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if self.should_terminate():
                        exit_now = True
                        exit_reason = "EOD Auto-Squareoff"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # Check for EOD even if no position, just to sleep
                if self.should_terminate():
                    self.logger.debug("Market hours over. Waiting.")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.is_time_window_open() and not self.entered_today:

                    if not self.limiter.allow():
                        self.logger.debug("Trade limiter active. Skipping entry.")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    atm_strike = self.get_atm_strike(chain)
                    if not atm_strike:
                        self.logger.warning("ATM strike not found.")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    premium = self.calculate_straddle_premium(chain, atm_strike)
                    self.logger.info(format_kv(spot=underlying_ltp, atm=atm_strike, premium=f"{premium:.2f}"))

                    if premium >= MIN_PREMIUM:
                        if self.debouncer.edge("ENTRY_SIGNAL", True):
                            self.logger.info("Entry signal detected. Placing Iron Condor orders...")

                            # Iron Condor:
                            # 1. Sell OTM2 Strangle (Short Legs)
                            # 2. Buy OTM5 Wings (Long Legs - Protection)

                            # Order: BUY first, then SELL (for margin benefit)
                            definitions = [
                                ("OTM5", "CE", "BUY"),
                                ("OTM5", "PE", "BUY"),
                                ("OTM2", "CE", "SELL"),
                                ("OTM2", "PE", "SELL")
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
                                        self.logger.info("Iron Condor positions tracked.")
                                    else:
                                        self.logger.error(f"Order Failed: {response.get('message')}")

                                except Exception as e:
                                    self.logger.error(f"Order Execution Error: {e}")
                            else:
                                self.logger.warning("Setup invalid (missing strikes). Skipping.")

                    else:
                        self.logger.debug(f"Premium {premium:.2f} < {MIN_PREMIUM}. Waiting.")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    try:
        strategy = NiftyDynamicIronCondorStrategy()
        strategy.run()
    except KeyboardInterrupt:
        print("Strategy stopped by user.")
    except Exception as e:
        print(f"Critical Error: {e}")
        sys.exit(1)
