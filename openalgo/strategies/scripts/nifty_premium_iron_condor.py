#!/usr/bin/env python3
"""
Nifty Premium Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM when straddle premium > 120, holds max 45m.
"""
import os
import sys
import time
from datetime import datetime, time as datetime_time

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

root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

try:
    from trading_utils import APIClient, is_market_open
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        safe_float,
        safe_int,
    )
    from strategy_common import SignalDebouncer, TradeLimiter, format_kv
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


class NiftyPremiumIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyPremiumIC")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.oc_client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=1, max_per_hour=1, cooldown_seconds=300)
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_fetch = 0
        self.all_open_legs = []
        self.entered_today = False
        self.last_trade_date = None

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_fetch > self.expiry_refresh_sec):
            try:
                res = self.oc_client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success":
                    expiries = res.get("data", [])
                    self.expiry = choose_nearest_expiry(expiries)
                    self.last_expiry_fetch = now
                    self.logger.info(f"Selected expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry: {e}")

    def _get_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" and pe.get("label") == "ATM":
                ce_ltp = safe_float(ce.get("ltp"))
                pe_ltp = safe_float(pe.get("ltp"))
                return ce_ltp + pe_ltp
        return 0.0

    def _close_position(self, exit_reason):
        if not self.all_open_legs:
            return

        self.logger.info(f"event=trade action=CLOSE_ALL reason={exit_reason}")

        for leg in self.all_open_legs:
            symbol = leg.get("symbol")
            if not symbol:
                continue

            original_action = leg.get("action", "BUY")
            close_action = "SELL" if original_action == "BUY" else "BUY"

            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0
                )
                self.logger.info(f"Trade response: Closed {symbol} ({close_action}) - {resp}")
            except Exception as e:
                self.logger.error(f"Failed to close leg {symbol}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def can_trade(self):
        now = datetime.now()
        current_time = now.time()

        if now.date() != self.last_trade_date:
            self.entered_today = False
            self.last_trade_date = now.date()

        if self.entered_today:
            return False

        # Time constraints: After 10:00 AM, before 14:30 PM
        if current_time < datetime_time(10, 0) or current_time > datetime_time(14, 30):
            return False

        return self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} - Nifty Premium Iron Condor")

        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.oc_client.optionchain(
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
                spot = chain_resp.get("underlying_ltp", 0.0)

                # EOD Square-off Check (15:15 IST)
                now_time = datetime.now().time()
                if now_time >= datetime_time(15, 15) and self.all_open_legs:
                    self._close_position("eod_squareoff")
                    time.sleep(self.sleep_seconds)
                    continue

                # Exit Management First
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # Entry Logic
                if not self.all_open_legs and self.can_trade():
                    straddle_premium = self._get_straddle_premium(chain)
                    self.logger.debug(format_kv(spot=spot, premium=straddle_premium, time=str(now_time)))

                    signal = self.debouncer.edge("entry_signal", straddle_premium > 120.0)

                    if signal:
                        self.logger.info(f"event=trade action=ENTRY signal=straddle_premium_gt_120 premium={straddle_premium}")
                        self.limiter.record()
                        self.entered_today = True

                        # Define the 4 legs (BUYS first for margin benefit)
                        # We buy OTM4 CE/PE, sell OTM2 CE/PE
                        order_legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        try:
                            resp = self.oc_client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.options_exchange,
                                expiry_date=self.expiry,
                                legs=order_legs
                            )

                            self.logger.info(f"Trade response: {resp}")

                            # Build the executed legs list
                            # Extract exact symbols from chain based on offset
                            executed_legs = []
                            short_legs = []
                            short_entry_prices = []

                            for leg_def in order_legs:
                                offset = leg_def["offset"]
                                opt_type = leg_def["option_type"]
                                action = leg_def["action"]

                                # Find symbol and ltp
                                symbol = None
                                ltp = 0.0
                                for item in chain:
                                    opt_data = item.get(opt_type.lower(), {})
                                    if opt_data.get("label") == offset:
                                        symbol = opt_data.get("symbol")
                                        ltp = safe_float(opt_data.get("ltp"))
                                        break

                                if symbol:
                                    exec_leg = {"symbol": symbol, "action": action, "quantity": self.quantity}
                                    executed_legs.append(exec_leg)
                                    if action == "SELL":
                                        short_legs.append(symbol)
                                        short_entry_prices.append(ltp)

                            self.all_open_legs = executed_legs

                            if short_legs:
                                self.tracker.add_legs(short_legs, short_entry_prices, side="SELL")

                        except Exception as e:
                            self.logger.error(f"Order placement failed: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyPremiumIronCondor().run()
