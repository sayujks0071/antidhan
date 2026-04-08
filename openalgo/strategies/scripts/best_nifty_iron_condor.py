#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters an Iron Condor after 10 AM if ATM straddle premium > 120 (Sells OTM2, Buys OTM4 wings).
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
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, utils_dir)
sys.path.insert(0, root_dir)

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

API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

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

# Configuration defaults via environment variables
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Risk/Reward parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "40.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

def get_atm_strike(chain):
    """Finds ATM strike locally to avoid importing from missing utils."""
    for item in chain:
        ce = item.get("ce", {})
        if ce.get("label") == "ATM":
            return safe_float(item.get("strike", 0.0))
    return None

def calculate_straddle_premium(chain, atm_strike):
    """Calculates ATM Straddle premium locally."""
    ce_ltp, pe_ltp = 0.0, 0.0
    for item in chain:
        if safe_float(item.get("strike", 0.0)) == atm_strike:
            ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0.0))
            pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0.0))
            break
    return ce_ltp + pe_ltp

class NiftyIronCondorStrategy:
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

        self.expiry = None
        self.last_expiry_check = 0

    def ensure_expiry(self):
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
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        now = datetime.now()
        # Enters after 10 AM, stop entering after 14:30
        if now.hour < 10 or (now.hour == 14 and now.minute > 30) or now.hour >= 15:
            return False
        return True

    def should_terminate(self):
        now = datetime.now()
        return now.hour >= 15 and now.minute >= 15

    def get_leg_details(self, chain, offset, option_type):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset:
                return {
                    "symbol": opt.get("symbol"),
                    "ltp": safe_float(opt.get("ltp", 0.0)),
                    "quantity": QUANTITY,
                    "product": PRODUCT
                }
        return None

    def _close_position(self, chain, reason):
        self.logger.info(f"event=trade action=CLOSE_POSITION reason={reason}")

        if not self.tracker.open_legs:
            return

        close_legs = []
        for leg in self.tracker.open_legs:
            close_action = "BUY" if leg.get("action") == "SELL" else "SELL"
            close_legs.append({
                "symbol": leg.get("symbol"),
                "action": close_action,
                "quantity": leg.get("quantity", QUANTITY),
                "product": leg.get("product", PRODUCT)
            })

        # Prioritize BUY over SELL for margin efficiency
        close_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            api_client = APIClient(api_key=API_KEY, host=HOST)
            for leg in close_legs:
                api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=leg["symbol"],
                    action=leg["action"],
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=leg["product"],
                    quantity=leg["quantity"],
                    position_size=0
                )
        except Exception as e:
            self.logger.error(f"Error closing positions: {e}")

        self.tracker.clear()

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME}...")
        while True:
            try:
                if not is_market_open():
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now or self.should_terminate():
                        reason = exit_reason if exit_now else "EOD Square-off"
                        self._close_position(chain, reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade() and not self.should_terminate():
                    atm_strike = get_atm_strike(chain)
                    if not atm_strike:
                        time.sleep(SLEEP_SECONDS)
                        continue

                    straddle_premium = calculate_straddle_premium(chain, atm_strike)
                    self.logger.debug(format_kv(spot="ATM", straddle_premium=straddle_premium))

                    # Condition: Premium > 120
                    signal_active = straddle_premium > 120.0

                    if self.debouncer.edge("entry_signal", signal_active):
                        if self.limiter.allow():
                            # BUY legs first, SELL legs second
                            legs_def = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY"},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY"},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL"},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL"},
                            ]

                            tracking_legs = []
                            entry_prices = []
                            api_legs = []
                            valid_setup = True

                            for l_def in legs_def:
                                details = self.get_leg_details(chain, l_def["offset"], l_def["option_type"])
                                if details:
                                    details["action"] = l_def["action"]
                                    tracking_legs.append(details)
                                    entry_prices.append(details["ltp"])
                                    api_legs.append({
                                        "offset": l_def["offset"],
                                        "option_type": l_def["option_type"],
                                        "action": l_def["action"],
                                        "quantity": QUANTITY,
                                        "product": PRODUCT
                                    })
                                else:
                                    valid_setup = False
                                    break

                            if valid_setup:
                                self.logger.info(f"event=trade action=ENTRY signal=Premium>{straddle_premium}")
                                try:
                                    response = self.client.optionsmultiorder(
                                        strategy=STRATEGY_NAME,
                                        underlying=UNDERLYING,
                                        exchange=UNDERLYING_EXCHANGE,
                                        expiry_date=self.expiry,
                                        legs=api_legs
                                    )

                                    if response.get("status") == "success":
                                        self.limiter.record()
                                        self.tracker.add_legs(tracking_legs, entry_prices, side="SELL")
                                        self.logger.info("Successfully entered Nifty Iron Condor.")
                                    else:
                                        self.logger.error(f"Order Failed: {response}")
                                except Exception as e:
                                    self.logger.error(f"Execution Error: {e}")

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
