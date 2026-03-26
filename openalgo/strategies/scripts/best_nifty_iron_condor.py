#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy selling OTM2 and buying OTM4 with dynamic exit logic.
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

sys.path.insert(0, root_dir)
sys.path.insert(0, utils_dir)

try:
    from trading_utils import is_market_open, APIClient
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        safe_float,
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


class BestNiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "BestNiftyIronCondor")
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
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "15"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.manual_expiry = os.getenv("EXPIRY_DATE", "")
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )

        self.expiry = self.manual_expiry
        self.last_expiry_refresh = 0

        self.all_open_legs = []
        self.entered_today = False
        self.reset_date = datetime.now().date()

    def ensure_expiry(self):
        now = time.time()
        if not self.manual_expiry and (not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec):
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res.get("status") == "success" and res.get("data"):
                self.expiry = choose_nearest_expiry(res["data"])
                self.last_expiry_refresh = now
                self.logger.info(f"Resolved nearest expiry: {self.expiry}")

    def check_reset(self):
        now_date = datetime.now().date()
        if now_date != self.reset_date:
            self.entered_today = False
            self.reset_date = now_date

    def get_atm_strike_and_premium(self, chain_resp, chain):
        atm_strike = chain_resp.get("atm_strike")
        if not atm_strike:
            for item in chain:
                if item.get("ce", {}).get("label") == "ATM":
                    atm_strike = item["strike"]
                    break

        straddle_premium = 0.0
        if atm_strike:
            for item in chain:
                if item["strike"] == atm_strike:
                    ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                    pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                    straddle_premium = ce_ltp + pe_ltp
                    break

        return atm_strike, straddle_premium

    def _close_position(self, chain, reason):
        self.logger.info(f"event=trade action=CLOSE reason={reason}")

        for leg in self.all_open_legs:
            # Reverse action
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            symbol = leg["symbol"]

            resp = self.api_client.placesmartorder(
                strategy=self.strategy_name,
                symbol=symbol,
                action=close_action,
                exchange=self.options_exchange,
                pricetype="MARKET",
                product=self.product,
                quantity=leg["quantity"],
                position_size=0
            )
            self.logger.info(f"Trade response (CLOSE {symbol}): {resp}")

        self.tracker.clear()
        self.all_open_legs = []

    def can_trade_now(self):
        now = datetime.now()
        # Only trade between 10:00 AM and 3:15 PM
        start_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = now.replace(hour=15, minute=15, second=0, microsecond=0)
        return start_time <= now < end_time

    def is_eod(self):
        now = datetime.now()
        eod_time = now.replace(hour=15, minute=15, second=0, microsecond=0)
        return now >= eod_time

    def run(self):
        self.logger.info(f"Starting {self.strategy_name}...")
        while True:
            try:
                self.check_reset()

                if not is_market_open():
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
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs or self.all_open_legs:
                    # Check EOD first
                    if self.is_eod():
                        self._close_position(chain, "eod_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS
                atm_strike, straddle_premium = self.get_atm_strike_and_premium(chain_resp, chain)
                spot = chain_resp.get("underlying_ltp", 0.0)

                self.logger.debug(format_kv(
                    spot=spot,
                    atm=atm_strike,
                    premium=f"{straddle_premium:.2f}",
                    time=datetime.now().strftime("%H:%M")
                ))

                # ENTRY LOGIC
                # Only enter if no open legs and within trading window
                if not self.tracker.open_legs and not self.all_open_legs and self.can_trade_now() and not self.entered_today:
                    condition = straddle_premium > self.min_straddle_premium

                    signal = self.debouncer.edge("entry_signal", condition and self.can_trade_now())

                    if signal and self.limiter.allow():
                        self.logger.info(format_kv(
                            event="trade",
                            action="ENTRY",
                            reason="premium_threshold_met",
                            premium=straddle_premium
                        ))

                        # Define legs: BUY wings first (OTM4), then SELL (OTM2)
                        legs_to_order = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.options_exchange,
                            expiry_date=self.expiry,
                            legs=legs_to_order
                        )

                        self.logger.info(f"Trade response (ENTRY): {resp}")
                        self.limiter.record()
                        self.entered_today = True

                        # In a real environment, optionsmultiorder response provides filled legs and prices.
                        # For backtesting/simulated environments, we extract symbols from chain
                        if resp.get("status") == "success":
                            # Match offsets from chain to build executed legs
                            executed_legs = []
                            for target_leg in legs_to_order:
                                offset = target_leg["offset"]
                                o_type = target_leg["option_type"].lower()

                                for item in chain:
                                    opt = item.get(o_type, {})
                                    if opt.get("label") == offset:
                                        executed_legs.append({
                                            "symbol": opt["symbol"],
                                            "action": target_leg["action"],
                                            "quantity": target_leg["quantity"],
                                            "entry_price": safe_float(opt.get("ltp"))
                                        })
                                        break

                            if len(executed_legs) == 4:
                                self.all_open_legs = executed_legs

                                # Track ONLY short legs in OptionPositionTracker
                                short_legs = [leg for leg in executed_legs if leg["action"] == "SELL"]
                                entry_prices = [leg["entry_price"] for leg in short_legs]

                                self.tracker.add_legs(short_legs, entry_prices, side="SELL")
                                self.logger.info(f"Position tracking started for short legs: {short_legs}")
                            else:
                                self.logger.error("Could not resolve all leg symbols from chain. Position tracking might fail.")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    BestNiftyIronCondor().run()
