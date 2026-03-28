#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters an Iron Condor after 10 AM when straddle premium > 120, selling OTM2 and buying OTM4.
"""
import os
import sys
import time
from datetime import datetime, time as dt_time

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
    from strategy_common import SignalDebouncer, TradeLedger, TradeLimiter, format_kv
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# Configuration Section
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "BestNiftyIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "12"))

# Strategy-specific parameters
SL_PCT = float(os.getenv("SL_PCT", "40"))
TP_PCT = float(os.getenv("TP_PCT", "50"))
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Time rules
ENTRY_START_TIME = dt_time(10, 0)
ENTRY_END_TIME = dt_time(14, 30)
EOD_EXIT_TIME = dt_time(15, 15)

# Premium constraints
MIN_STRADDLE_PREMIUM = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

# API Key retrieval (MANDATORY)
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

class StrategyClass:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(max_per_day=MAX_ORDERS_PER_DAY, max_per_hour=MAX_ORDERS_PER_HOUR, cooldown_seconds=COOLDOWN_SECONDS)

        # Strategy state
        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.reset_date = datetime.now().date()
        self.all_open_legs = [] # Tracker only gets short legs, this stores all

        self.logger.info(f"Initialized {STRATEGY_NAME}. SL={SL_PCT}%, TP={TP_PCT}%, MaxHold={MAX_HOLD_MIN}m")

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > EXPIRY_REFRESH_SEC:
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res and res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.last_expiry_refresh = now
                    self.logger.info(f"Selected expiry: {self.expiry}")
                else:
                    self.logger.error("Could not find valid expiry date")
            else:
                self.logger.error("Failed to fetch expiry dates")

    def _get_atm_strike(self, chain_resp):
        # Use direct key if available
        if "atm_strike" in chain_resp:
            return safe_float(chain_resp["atm_strike"])

        # Fallback to searching chain
        chain = chain_resp.get("chain", [])
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return safe_float(item.get("strike"))
        return 0.0

    def _get_straddle_premium(self, chain, atm_strike):
        for item in chain:
            if safe_float(item.get("strike")) == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0.0))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0.0))
                return ce_ltp + pe_ltp
        return 0.0

    def can_trade_now(self):
        """Time-based and daily limits check."""
        now = datetime.now()

        if now.date() != self.reset_date:
            self.entered_today = False
            self.reset_date = now.date()

        if self.entered_today:
            return False

        current_time = now.time()

        if current_time < ENTRY_START_TIME or current_time > ENTRY_END_TIME:
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        """Closes all legs individually since optionsmultiorder shouldn't be used with relative offsets for exits"""
        self.logger.info(f"event=trade action=CLOSE reason={reason}")

        # We need to map chain LTPs to log the exit
        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        for leg in self.all_open_legs:
            symbol = leg.get("symbol")
            if not symbol: continue

            # Reverse action
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"

            from trading_utils import APIClient
            temp_client = APIClient(api_key=API_KEY, host=HOST)

            resp = temp_client.placesmartorder(
                strategy=STRATEGY_NAME,
                symbol=symbol,
                action=close_action,
                exchange=OPTIONS_EXCHANGE,
                pricetype="MARKET",
                product=PRODUCT,
                quantity=QUANTITY,
                position_size=0
            )

            exit_price = ltp_map.get(symbol, 0.0)
            self.logger.info(format_kv(symbol=symbol, action=close_action, exit_price=exit_price, resp=resp.get("status", "unknown")))

        self.tracker.clear()
        self.all_open_legs = []

    def _enter_position(self, chain):
        self.logger.info("Condition met. Placing Iron Condor order.")

        # BUY legs execute first for margin efficiency
        legs = [
            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
        ]

        response = self.client.optionsmultiorder(
            strategy=STRATEGY_NAME,
            underlying=UNDERLYING,
            exchange=OPTIONS_EXCHANGE,  # NFO for multiorder
            expiry_date=self.expiry,
            legs=legs
        )

        if response.get("status") == "success":
            self.logger.info(f"event=trade action=ENTRY response={response}")
            self.entered_today = True
            self.limiter.record()

            # Extract actual symbols and entry prices from chain to track
            # OpenAlgo multiorder doesn't return fill prices, we use current LTP
            otm2_ce = otm2_pe = otm4_ce = otm4_pe = None

            for item in chain:
                if item.get("ce", {}).get("label") == "OTM2": otm2_ce = item["ce"]
                if item.get("pe", {}).get("label") == "OTM2": otm2_pe = item["pe"]
                if item.get("ce", {}).get("label") == "OTM4": otm4_ce = item["ce"]
                if item.get("pe", {}).get("label") == "OTM4": otm4_pe = item["pe"]

            if otm2_ce and otm2_pe and otm4_ce and otm4_pe:
                # Store all legs for closing
                self.all_open_legs = [
                    {"symbol": otm4_ce["symbol"], "action": "BUY", "entry_price": safe_float(otm4_ce["ltp"]), "quantity": QUANTITY},
                    {"symbol": otm4_pe["symbol"], "action": "BUY", "entry_price": safe_float(otm4_pe["ltp"]), "quantity": QUANTITY},
                    {"symbol": otm2_ce["symbol"], "action": "SELL", "entry_price": safe_float(otm2_ce["ltp"]), "quantity": QUANTITY},
                    {"symbol": otm2_pe["symbol"], "action": "SELL", "entry_price": safe_float(otm2_pe["ltp"]), "quantity": QUANTITY}
                ]

                # Only track short legs for SL/TP evaluation to avoid false exits
                short_legs = [
                    {"symbol": otm2_ce["symbol"], "action": "SELL", "quantity": QUANTITY},
                    {"symbol": otm2_pe["symbol"], "action": "SELL", "quantity": QUANTITY}
                ]
                entry_prices = [safe_float(otm2_ce["ltp"]), safe_float(otm2_pe["ltp"])]

                self.tracker.add_legs(short_legs, entry_prices, side="SELL")
                self.logger.info(f"Tracking legs: {short_legs} at prices {entry_prices}")
            else:
                self.logger.error("Could not find all required legs in chain to track.")
                # We placed the order but can't track it! Fallback cleanup
                self.all_open_legs = []
        else:
            self.logger.error(f"Order failed: {response}")

    def run(self):
        self.logger.info("Starting strategy loop...")
        while True:
            try:
                if not is_market_open():
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # EOD Exit Check
                now = datetime.now()
                if now.time() >= EOD_EXIT_TIME:
                    if self.tracker.open_legs:
                        # fetch chain just to get closing prices
                        chain_resp = self.client.optionchain(
                            underlying=UNDERLYING,
                            exchange=UNDERLYING_EXCHANGE,
                            expiry_date=self.expiry,
                            strike_count=STRIKE_COUNT
                        )
                        chain = chain_resp.get("chain", [])
                        self._close_position(chain, "eod_square_off")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE, # NSE_INDEX for optionchain fetch
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # CALCULATE INDICATORS
                atm_strike = self._get_atm_strike(chain_resp)
                if atm_strike == 0.0:
                    time.sleep(SLEEP_SECONDS)
                    continue

                straddle_prem = self._get_straddle_premium(chain, atm_strike)

                self.logger.info(format_kv(
                    spot=safe_float(chain_resp.get("underlying_ltp")),
                    atm=atm_strike,
                    straddle=straddle_prem,
                    open_pos=len(self.tracker.open_legs) > 0,
                    can_trade=self.can_trade_now()
                ))

                # ENTRY LOGIC
                if not self.tracker.open_legs:
                    # Condition: straddle premium > 120
                    condition = straddle_prem > MIN_STRADDLE_PREMIUM

                    # Ensure time check is tied to edge detection to avoid burning the signal early
                    is_ready = condition and self.can_trade_now()

                    if self.debouncer.edge("enter_ic", is_ready):
                        self._enter_position(chain)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                import traceback
                self.logger.error(traceback.format_exc())

            time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    StrategyClass().run()
