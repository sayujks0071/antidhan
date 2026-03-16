#!/usr/bin/env python3
"""
NIFTY Iron Condor Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Enters an Iron Condor after 10 AM if straddle premium > 120. Sells OTM2 CE/PE, buys OTM4 CE/PE. Max hold 45m.
"""
import os
import sys
import time
from datetime import datetime, time as dtime

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
        safe_int
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

class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "NIFTY_IRON_CONDOR")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk & Reward
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Rate Limiting
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # Internal State
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()
        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_check = 0
        self.all_open_legs = [] # Tracks all legs for closing
        self.entered_today = False
        self.reset_date = datetime.now().date()

        self.logger.info(f"Initialized {self.strategy_name} - SL: {self.sl_pct}%, TP: {self.tp_pct}%, Max Hold: {self.max_hold_min}m")

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    self.expiry = choose_nearest_expiry(res.get("data"))
                    self.last_expiry_check = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry: {e}")

    def _check_daily_reset(self):
        now_date = datetime.now().date()
        if now_date != self.reset_date:
            self.entered_today = False
            self.reset_date = now_date

    def can_trade(self):
        now = datetime.now().time()
        # Do not enter before 10:00 AM
        if now < dtime(10, 0):
            return False
        # Do not enter after 3:15 PM (15:15)
        if now >= dtime(15, 15):
            return False
        if self.entered_today:
            return False
        return self.limiter.allow()

    def _close_position(self, chain, reason):
        self.logger.info(f"event=trade action=CLOSE_ALL reason={reason} msg='Closing Iron Condor position'")
        # For simplicity and robust closing, iterate over all open legs we recorded and close them
        for leg in self.all_open_legs:
            # Reverse action
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg["quantity"],
                    position_size=0
                )
                self.logger.info(f"Closed leg {leg['symbol']}: {resp}")
            except Exception as e:
                self.logger.error(f"Failed to close leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def get_option_by_offset(self, chain, offset, opt_type):
        for strike_data in chain:
            opt = strike_data.get(opt_type.lower())
            if opt and opt.get("label") == offset:
                return opt
        return None

    def run(self):
        self.logger.info("Starting Nifty Iron Condor strategy loop...")
        while True:
            try:
                self._check_daily_reset()

                if not is_market_open():
                    # EOD square off check (close before 15:15)
                    now = datetime.now().time()
                    if now >= dtime(15, 15) and self.tracker.open_legs:
                        self.logger.info("EOD Square-off triggered.")
                        # Need chain for prices if we cared about logging PnL, but we just close
                        self._close_position([], "eod_squareoff")
                    time.sleep(self.sleep_seconds)
                    continue

                # Normal EOD square off inside market hours
                now = datetime.now().time()
                if now >= dtime(15, 15) and self.tracker.open_legs:
                    self.logger.info("EOD Square-off triggered.")
                    self._close_position([], "eod_squareoff")

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )
                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")
                spot_price = chain_resp.get("underlying_ltp")

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    atm_ce = self.get_option_by_offset(chain, "ATM", "CE")
                    atm_pe = self.get_option_by_offset(chain, "ATM", "PE")
                    if atm_ce and atm_pe:
                        straddle_premium = safe_float(atm_ce.get("ltp", 0.0)) + safe_float(atm_pe.get("ltp", 0.0))
                    else:
                        straddle_premium = 0.0

                    self.logger.debug(format_kv(
                        spot=spot_price,
                        atm=atm_strike,
                        straddle_premium=straddle_premium
                    ))

                    signal_condition = straddle_premium > self.min_straddle_premium

                    if self.debouncer.edge("enter_ic", signal_condition):
                        self.logger.info(f"Signal triggered: Premium {straddle_premium} > {self.min_straddle_premium}")

                        # Extract symbols and prices for short legs and wings
                        # Iron Condor: Sell OTM2 CE/PE, Buy OTM4 CE/PE
                        sell_ce = self.get_option_by_offset(chain, "OTM2", "CE")
                        sell_pe = self.get_option_by_offset(chain, "OTM2", "PE")
                        buy_ce = self.get_option_by_offset(chain, "OTM4", "CE")
                        buy_pe = self.get_option_by_offset(chain, "OTM4", "PE")

                        if sell_ce and sell_pe and buy_ce and buy_pe:
                            self.limiter.record()
                            self.entered_today = True

                            # Place multi-leg order. BUY first for margin benefit.
                            legs = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            ]

                            self.logger.info(f"event=trade action=ENTRY strategy={self.strategy_name} msg='Placing Iron Condor order'")

                            try:
                                response = self.client.optionsmultiorder(
                                    strategy=self.strategy_name,
                                    underlying=self.underlying,
                                    exchange=self.exchange,
                                    expiry_date=self.expiry,
                                    legs=legs
                                )
                                self.logger.info(f"Trade response: {response}")

                                # Track only the short legs for exit conditions (so protective buys don't trigger SL/TP)
                                short_legs_to_track = [
                                    {"symbol": sell_ce["symbol"], "action": "SELL", "quantity": self.quantity},
                                    {"symbol": sell_pe["symbol"], "action": "SELL", "quantity": self.quantity}
                                ]
                                entry_prices = {
                                    sell_ce["symbol"]: sell_ce["ltp"],
                                    sell_pe["symbol"]: sell_pe["ltp"]
                                }
                                self.tracker.add_legs(short_legs_to_track, entry_prices, side="SELL")

                                # Keep all open legs in state for clean closing
                                self.all_open_legs = [
                                    {"symbol": buy_ce["symbol"], "action": "BUY", "quantity": self.quantity},
                                    {"symbol": buy_pe["symbol"], "action": "BUY", "quantity": self.quantity},
                                    {"symbol": sell_ce["symbol"], "action": "SELL", "quantity": self.quantity},
                                    {"symbol": sell_pe["symbol"], "action": "SELL", "quantity": self.quantity}
                                ]
                            except Exception as e:
                                self.logger.error(f"Failed to place multi-leg order: {e}")
                        else:
                            self.logger.warning("Could not find all required legs for Iron Condor (OTM2, OTM4).")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    strategy = NiftyIronCondorStrategy()
    strategy.run()
