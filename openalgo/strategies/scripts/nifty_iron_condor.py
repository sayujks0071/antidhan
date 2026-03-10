#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM when straddle premium > 120, sells OTM2/buys OTM4.
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
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.exchange_underlying = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.exchange_options = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "120"), 120)
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "30"), 30)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)

        self.max_orders_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        # Strategy specific params
        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"), 120.0)

        # State
        self.expiry = None
        self.last_expiry_check = 0
        self.entered_today = False
        self.last_trade_date = None

        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.all_open_legs = []

        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_day,
            max_per_hour=self.max_orders_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check) > self.expiry_refresh_sec:
            manual_expiry = os.getenv("EXPIRY_DATE")
            if manual_expiry:
                self.expiry = manual_expiry
                self.last_expiry_check = now
                self.logger.info(f"Using manual expiry: {self.expiry}")
                return

            try:
                res = self.client.expiry(self.underlying, self.exchange_options, "options")
                if res and res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        self.expiry = choose_nearest_expiry(dates)
                        self.last_expiry_check = now
                        self.logger.info(f"Resolved nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error resolving expiry: {e}")

    def reset_daily_state(self):
        today = datetime.now().date()
        if self.last_trade_date != today:
            self.entered_today = False
            self.last_trade_date = today

    def can_trade(self):
        now = datetime.now()
        # Enters after 10 AM, exits before 3:15 PM
        if now.hour < 10:
            return False
        if now.hour == 15 and now.minute >= 15:
            return False
        if now.hour > 15:
            return False

        self.reset_daily_state()
        if self.entered_today:
            return False

        if not self.limiter.allow():
            return False

        return True

    def get_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" and pe.get("label") == "ATM":
                ce_ltp = safe_float(ce.get("ltp"))
                pe_ltp = safe_float(pe.get("ltp"))
                return ce_ltp + pe_ltp
        return 0.0

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position, reason: {reason}")
        for leg in self.all_open_legs:
            close_action = "BUY" if leg.get("action") == "SELL" else "SELL"
            try:
                self.logger.info(f"Closing leg {leg.get('symbol')} with action {close_action}")
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg.get("symbol"),
                    action=close_action,
                    exchange=self.exchange_options,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg.get("quantity", self.quantity),
                    position_size=0
                )
                self.logger.info(f"Close response: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg.get('symbol')}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def find_leg_symbol_and_price(self, chain, offset, opt_type):
        for item in chain:
            opt = item.get(opt_type.lower(), {})
            if opt.get("label") == offset:
                return opt.get("symbol"), safe_float(opt.get("ltp"))
        return None, 0.0

    def enter_position(self, chain, spot):
        self.logger.info(f"event=trade action=ENTRY strategy={self.strategy_name}")
        # BUY legs before SELL legs for margin efficiency
        legs = [
            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
        ]

        try:
            response = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.exchange_underlying,
                expiry_date=self.expiry,
                legs=legs
            )
            self.logger.info(f"Trade response: {response}")

            self.limiter.record()
            self.entered_today = True

            all_resolved_legs = []
            sell_legs = []
            entry_prices = []

            for leg in legs:
                sym, ltp = self.find_leg_symbol_and_price(chain, leg["offset"], leg["option_type"])
                if sym:
                    track_leg = leg.copy()
                    track_leg["symbol"] = sym
                    all_resolved_legs.append(track_leg)

                    if leg.get("action") == "SELL":
                        sell_legs.append(track_leg)
                        entry_prices.append(ltp)

            self.all_open_legs = all_resolved_legs

            if sell_legs and len(sell_legs) == len(entry_prices):
                self.tracker.add_legs(sell_legs, entry_prices, side="SELL")
                self.logger.info(f"Tracking SELL legs: {[l['symbol'] for l in sell_legs]} with prices {entry_prices}")
            else:
                self.logger.warning("Failed to properly resolve SELL legs from option chain")

        except Exception as e:
            self.logger.error(f"Error entering position: {e}")

    def run(self):
        self.logger.info(f"Starting {self.strategy_name}...")
        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.exchange_underlying,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = safe_float(chain_resp.get("underlying_ltp"))

                # EXIT MANAGEMENT FIRST
                now = datetime.now()
                eod_exit = (now.hour == 15 and now.minute >= 15) or (now.hour > 15)

                if self.tracker.open_legs:
                    if eod_exit:
                        self._close_position(chain, "EOD_Squareoff")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS
                straddle_prem = self.get_straddle_premium(chain)
                self.logger.debug(format_kv(spot=spot, straddle_prem=straddle_prem, can_trade=self.can_trade()))

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade() and not eod_exit:
                    entry_signal = straddle_prem > self.min_straddle_premium

                    if self.debouncer.edge("enter_ic", entry_signal):
                        self.enter_position(chain, spot)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    StrategyClass().run()
