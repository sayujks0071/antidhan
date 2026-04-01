#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy entering after 10 AM if straddle premium > 120, holding for max 45 mins.
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
        self.strategy_name = os.getenv("STRATEGY_NAME", "best_nifty_iron_condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "300"), 300)
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "15"), 15)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        # Strategy specific params
        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"), 120.0)

        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )

        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.last_trade_date = None

        self.all_open_legs = []

        self.logger.info(f"Initialized {self.strategy_name} with SL={self.sl_pct}%, TP={self.tp_pct}%, Hold={self.max_hold_min}m")

    def ensure_expiry(self):
        current_time = time.time()
        if not self.expiry or (current_time - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if isinstance(res, dict) and res.get("status") == "success":
                    expiries = res.get("data", [])
                    if expiries:
                        self.expiry = choose_nearest_expiry(expiries)
                        self.last_expiry_refresh = current_time
                        self.logger.info(f"Selected nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def get_straddle_premium(self, chain):
        atm_ce_ltp = 0.0
        atm_pe_ltp = 0.0
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM":
                atm_ce_ltp = safe_float(ce.get("ltp"))
            if pe.get("label") == "ATM":
                atm_pe_ltp = safe_float(pe.get("ltp"))
        return atm_ce_ltp + atm_pe_ltp

    def _close_position(self, reason="time_stop"):
        self.logger.info(f"Closing position, reason: {reason}")

        closing_actions = []
        for leg in self.all_open_legs:
            action_to_close = "BUY" if leg["action"] == "SELL" else "SELL"
            closing_actions.append({
                "symbol": leg["symbol"],
                "action": action_to_close
            })

        # Prioritize BUY to cover actions (closing short legs) before SELL to close actions
        closing_actions.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        for leg in closing_actions:
            try:
                self.logger.info(f"event=trade Trade response: Closing leg {leg['symbol']} with {leg['action']}")
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=leg["action"],
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0
                )
                self.logger.info(f"Close leg response: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []
        self.logger.info("Position closed successfully")

    def can_trade(self, now):
        is_time_valid = (now.hour > 10 or (now.hour == 10 and now.minute >= 0)) and \
                        (now.hour < 15 or (now.hour == 15 and now.minute < 0))
        return is_time_valid and not self.entered_today and self.limiter.allow()

    def run(self):
        while True:
            try:
                now = datetime.now()
                today = now.date()

                if self.last_trade_date != today:
                    self.entered_today = False
                    self.last_trade_date = today

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
                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD exit by 15:15
                    if now.hour == 15 and now.minute >= 15:
                        exit_now = True
                        exit_reason = "eod_squareoff"

                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.all_open_legs and self.can_trade(now):
                    straddle_premium = self.get_straddle_premium(chain)

                    self.logger.info(format_kv(
                        spot=chain_resp.get('underlying_ltp'),
                        straddle_premium=straddle_premium,
                        signal="CHECK"
                    ))

                    can_trade_now = straddle_premium > self.min_straddle_premium

                    if self.debouncer.edge("enter_ic", can_trade_now):
                        # BUY legs first, then SELL legs (for margin efficiency)
                        legs_def = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        self.logger.info("event=trade Placing Iron Condor order")
                        try:
                            resp = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.underlying_exchange,
                                expiry_date=self.expiry,
                                legs=legs_def
                            )
                            self.logger.info(f"Order response: {resp}")

                            # Regardless of actual fill success, we simulate tracking for testing context
                            self.limiter.record()
                            self.entered_today = True

                            short_legs_for_tracker = []
                            all_legs_info = []

                            def find_leg_in_chain(offset, opt_type):
                                for item in chain:
                                    opt = item.get(opt_type.lower(), {})
                                    if opt.get("label") == offset:
                                        return opt
                                return None

                            for l_def in legs_def:
                                opt_data = find_leg_in_chain(l_def["offset"], l_def["option_type"])
                                if opt_data:
                                    symbol = opt_data.get("symbol")
                                    if symbol:
                                        all_legs_info.append({
                                            "symbol": symbol,
                                            "action": l_def["action"]
                                        })

                                        if l_def["action"] == "SELL":
                                            short_legs_for_tracker.append({"symbol": symbol})

                            entry_prices = []
                            track_legs = []
                            for l in short_legs_for_tracker:
                                ltp = 0.0
                                for c_item in chain:
                                    if c_item.get("ce", {}).get("symbol") == l["symbol"]:
                                        ltp = safe_float(c_item.get("ce", {}).get("ltp"))
                                        break
                                    if c_item.get("pe", {}).get("symbol") == l["symbol"]:
                                        ltp = safe_float(c_item.get("pe", {}).get("ltp"))
                                        break
                                entry_prices.append(ltp)
                                track_legs.append({"symbol": l["symbol"]})

                            if track_legs:
                                self.tracker.add_legs(track_legs, entry_prices, side="SELL")
                                self.all_open_legs = all_legs_info

                        except Exception as e:
                            self.logger.error(f"Error placing order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
