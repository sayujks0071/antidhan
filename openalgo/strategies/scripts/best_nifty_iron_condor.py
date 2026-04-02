#!/usr/bin/env python3
"""
Best Nifty Iron Condor Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120, sells OTM2, buys OTM4.
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
    from trading_utils import APIClient, is_market_open
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        normalize_expiry,
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


class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "120"), 120)
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "15"), 15)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120"), 120.0)

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
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
        self.current_date = datetime.now().date()
        self.all_open_legs = []

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res.get("status") == "success" and res.get("data"):
                    expiries = res.get("data", [])
                    nearest = choose_nearest_expiry(expiries)
                    if nearest:
                        if nearest != self.expiry:
                            self.logger.info(format_kv(event="expiry_update", old=self.expiry, new=nearest))
                        self.expiry = nearest
                        self.last_expiry_refresh = now
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry: {e}")

    def _close_position(self, chain, reason):
        self.logger.info(format_kv(event="trade", action="CLOSE", reason=reason, legs=len(self.all_open_legs)))

        # Sort legs to prioritize BUY (to cover short legs) before SELL (to close long legs)
        sorted_legs = sorted(self.all_open_legs, key=lambda leg: 0 if leg.get("action") == "SELL" else 1)

        for leg in sorted_legs:
            try:
                close_action = "BUY" if leg.get("action") == "SELL" else "SELL"
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0
                )
                self.logger.info(format_kv(event="trade_leg_closed", symbol=leg["symbol"], action=close_action, resp=resp.get("status")))
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def can_trade(self):
        now = datetime.now()
        # Ensure we're past 10:00 AM
        if now.hour < 10:
            return False
        # Do not enter after 14:30 (2:30 PM)
        if now.hour >= 15 or (now.hour == 14 and now.minute >= 30):
            return False
        if self.entered_today:
            return False
        return self.limiter.allow()

    def get_straddle_premium(self, chain):
        atm_ce = None
        atm_pe = None
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" and pe.get("label") == "ATM":
                atm_ce = ce
                atm_pe = pe
                break

        if atm_ce and atm_pe:
            return safe_float(atm_ce.get("ltp", 0.0)) + safe_float(atm_pe.get("ltp", 0.0))
        return 0.0

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} strategy...")

        while True:
            try:
                now_date = datetime.now().date()
                if now_date != self.current_date:
                    self.current_date = now_date
                    self.entered_today = False

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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0.0))

                now = datetime.now()
                is_eod = (now.hour == 15 and now.minute >= 15)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs or self.all_open_legs:
                    if is_eod:
                        self._close_position(chain, "eod_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and not self.all_open_legs and self.can_trade() and not is_eod:
                    straddle_premium = self.get_straddle_premium(chain)

                    self.logger.debug(format_kv(spot=underlying_ltp, premium=straddle_premium, min_required=self.min_straddle_premium))

                    if straddle_premium > self.min_straddle_premium:
                        signal = self.debouncer.edge("entry_signal", True)
                        if signal:
                            self.logger.info(format_kv(event="entry_signal", reason="premium_high", premium=straddle_premium))

                            # Place multi-leg order
                            # BUY OTM4 CE/PE, SELL OTM2 CE/PE
                            # Buy legs execute first for margin efficiency
                            legs = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            ]

                            try:
                                resp = self.client.optionsmultiorder(
                                    strategy=self.strategy_name,
                                    underlying=self.underlying,
                                    exchange=self.underlying_exchange,
                                    expiry_date=self.expiry,
                                    legs=legs
                                )

                                if resp.get("status") == "success":
                                    self.logger.info("Trade response: multi_order_placed")
                                    self.limiter.record()
                                    self.entered_today = True

                                    # Find actual execution symbols from chain to track
                                    short_legs_to_track = []
                                    all_legs_opened = []

                                    for req_leg in legs:
                                        for item in chain:
                                            opt_data = item.get(req_leg["option_type"].lower(), {})
                                            if opt_data.get("label") == req_leg["offset"]:
                                                leg_info = {
                                                    "symbol": opt_data.get("symbol"),
                                                    "action": req_leg["action"],
                                                    "entry_price": safe_float(opt_data.get("ltp")),
                                                    "quantity": self.quantity
                                                }
                                                all_legs_opened.append(leg_info)

                                                if req_leg["action"] == "SELL":
                                                    short_legs_to_track.append(leg_info)
                                                break

                                    if short_legs_to_track:
                                        self.all_open_legs = all_legs_opened
                                        entry_prices = [leg["entry_price"] for leg in short_legs_to_track]
                                        self.tracker.add_legs(short_legs_to_track, entry_prices, side="SELL")
                                        self.logger.info(format_kv(event="position_opened", short_legs=len(short_legs_to_track)))

                            except Exception as e:
                                self.logger.error(f"Error placing multi order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass = NiftyIronCondorStrategy
    StrategyClass().run()
