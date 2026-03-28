#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy that enters after 10 AM if the ATM straddle premium is > 120. Sells OTM2, Buys OTM4.
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

        self.strategy_name = os.getenv("STRATEGY_NAME", "best_nifty_iron_condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=self.max_orders_per_day, max_per_hour=self.max_orders_per_hour, cooldown_seconds=self.cooldown_seconds)
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.all_open_legs = []

    def ensure_expiry(self):
        now = time.time()
        manual_expiry = os.getenv("EXPIRY_DATE")
        if manual_expiry:
            self.expiry = normalize_expiry(manual_expiry)
            return

        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res and res.get("status") == "success" and res.get("data"):
                self.expiry = choose_nearest_expiry(res.get("data"))
                self.last_expiry_refresh = now
                self.logger.info(f"Resolved nearest expiry: {self.expiry}")

    def can_trade(self):
        if self.entered_today:
            return False

        now = datetime.now()

        # Don't enter before 10 AM
        if now.hour < 10:
            return False

        # Don't enter after 3 PM
        if now.hour >= 15:
            return False

        return self.limiter.allow()

    def _close_position(self, chain, exit_reason):
        if not self.all_open_legs:
            return

        self.logger.info(f"event=trade Closing position. Reason: {exit_reason}")

        from trading_utils import APIClient
        api_client = APIClient(api_key=API_KEY, host=HOST)

        for leg in self.all_open_legs:
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            self.logger.info(format_kv(symbol=leg["symbol"], action=close_action, reason=exit_reason))

            resp = api_client.placesmartorder(
                strategy=self.strategy_name,
                symbol=leg["symbol"],
                action=close_action,
                exchange=self.options_exchange,
                pricetype="MARKET",
                product=self.product,
                quantity=leg["quantity"],
                position_size=0
            )
            self.logger.info(f"Trade response: {resp}")

        self.tracker.clear()
        self.all_open_legs = []

    def get_straddle_premium(self, chain, atm_strike):
        ce_ltp = 0.0
        pe_ltp = 0.0
        for item in chain:
            if item.get("strike") == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                break
        return ce_ltp + pe_ltp

    def run(self):
        self.logger.info(f"Starting strategy: {self.strategy_name}")
        while True:
            try:
                if not is_market_open():
                    # Reset daily flag when market is closed
                    now = datetime.now()
                    if now.hour > 16:
                        self.entered_today = False
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )
                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")

                # EXIT MANAGEMENT FIRST
                now = datetime.now()
                # Force EOD exit at 3:15 PM
                if self.tracker.open_legs and now.hour == 15 and now.minute >= 15:
                    self._close_position(chain, "EOD_square_off")
                    time.sleep(self.sleep_seconds)
                    continue

                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    straddle_premium = self.get_straddle_premium(chain, atm_strike)
                    self.logger.debug(format_kv(spot=chain_resp.get("underlying_ltp"), atm=atm_strike, premium=straddle_premium))

                    condition = straddle_premium > self.min_straddle_premium
                    if self.debouncer.edge("entry_signal", condition):
                        self.logger.info(format_kv(event="signal_triggered", spot=chain_resp.get("underlying_ltp"), atm=atm_strike, premium=straddle_premium))

                        # Find legs in chain
                        otm2_ce = None
                        otm2_pe = None
                        otm4_ce = None
                        otm4_pe = None

                        for item in chain:
                            if item.get("ce", {}).get("label") == "OTM2":
                                otm2_ce = item["ce"]
                            if item.get("pe", {}).get("label") == "OTM2":
                                otm2_pe = item["pe"]
                            if item.get("ce", {}).get("label") == "OTM4":
                                otm4_ce = item["ce"]
                            if item.get("pe", {}).get("label") == "OTM4":
                                otm4_pe = item["pe"]

                        if not all([otm2_ce, otm2_pe, otm4_ce, otm4_pe]):
                            self.logger.warning("Could not find all required legs (OTM2, OTM4) in chain")
                            time.sleep(self.sleep_seconds)
                            continue

                        legs_req = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        self.logger.info(f"event=trade Placing Iron Condor order: {legs_req}")
                        response = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.options_exchange,
                            expiry_date=self.expiry,
                            legs=legs_req
                        )
                        self.logger.info(f"Trade response: {response}")

                        # Assuming order was successful for tracking
                        short_legs = [
                            {"symbol": otm2_ce["symbol"], "action": "SELL", "quantity": self.quantity},
                            {"symbol": otm2_pe["symbol"], "action": "SELL", "quantity": self.quantity}
                        ]

                        self.all_open_legs = [
                            {"symbol": otm4_ce["symbol"], "action": "BUY", "quantity": self.quantity},
                            {"symbol": otm4_pe["symbol"], "action": "BUY", "quantity": self.quantity},
                            {"symbol": otm2_ce["symbol"], "action": "SELL", "quantity": self.quantity},
                            {"symbol": otm2_pe["symbol"], "action": "SELL", "quantity": self.quantity}
                        ]

                        short_prices = [safe_float(otm2_ce.get("ltp")), safe_float(otm2_pe.get("ltp"))]
                        self.tracker.add_legs(short_legs, short_prices, side="SELL")

                        self.limiter.record()
                        self.entered_today = True

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
