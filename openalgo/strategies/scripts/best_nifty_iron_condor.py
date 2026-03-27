#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when ATM straddle premium > 120, sells OTM2 and buys OTM4.
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


class BestNiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "BestNiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), default=1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), default=12)

        # Risk & Timing Parameters
        self.sl_pct = safe_float(os.getenv("SL_PCT", "40"), default=40)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50"), default=50)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), default=45)
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "30"), default=30)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), default=3600)
        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120"), default=120)

        # Setup Clients
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(
            max_per_day=safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), default=1),
            max_per_hour=safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), default=1),
            cooldown_seconds=safe_int(os.getenv("COOLDOWN_SECONDS", "300"), default=300)
        )
        self.debouncer = SignalDebouncer()

        # Strategy State
        self.expiry = os.getenv("EXPIRY_DATE", None)
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
                    dates = res["data"]
                    nearest = choose_nearest_expiry(dates)
                    if nearest:
                        self.expiry = nearest
                        self.last_expiry_refresh = now
                        self.logger.info(format_kv(event="expiry_updated", expiry=self.expiry))
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        now = datetime.now()

        # Reset daily state
        if now.date() != self.current_date:
            self.entered_today = False
            self.current_date = now.date()

        # Time checks
        current_time = now.time()
        start_time = dt_time(10, 0)
        end_time = dt_time(14, 30)

        if current_time < start_time or current_time > end_time:
            return False

        if self.entered_today:
            return False

        return self.limiter.allow()

    def _close_position(self, reason):
        if not self.all_open_legs:
            return

        self.logger.info(format_kv(event="trade", action="EXIT", reason=reason, legs=len(self.all_open_legs)))

        for leg in self.all_open_legs:
            try:
                # Reverse action to close
                exit_action = "BUY" if leg["action"] == "SELL" else "SELL"
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=exit_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0
                )
                self.logger.info(f"Trade response: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def get_atm_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" and pe.get("label") == "ATM":
                return safe_float(ce.get("ltp")) + safe_float(pe.get("ltp"))
        return 0.0

    def get_leg_by_offset(self, chain, option_type, target_label):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == target_label:
                return opt
        return None

    def execute_entry(self, chain):
        # Identify legs
        ce_sell = self.get_leg_by_offset(chain, "CE", "OTM2")
        pe_sell = self.get_leg_by_offset(chain, "PE", "OTM2")
        ce_buy = self.get_leg_by_offset(chain, "CE", "OTM4")
        pe_buy = self.get_leg_by_offset(chain, "PE", "OTM4")

        if not all([ce_sell, pe_sell, ce_buy, pe_buy]):
            self.logger.warning("Could not find all required legs for Iron Condor")
            return

        # Prepare legs for multi-order (BUY legs first for margin)
        legs = [
            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
        ]

        self.logger.info(format_kv(event="trade", action="ENTRY", type="IRON_CONDOR"))

        try:
            resp = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.underlying_exchange,
                expiry_date=self.expiry,
                legs=legs
            )
            self.logger.info(f"Trade response: {resp}")

            if resp.get("status") == "success":
                # Track state
                self.entered_today = True
                self.limiter.record()

                # Setup risk tracking (only short legs for PnL calculation)
                short_legs = [
                    {"symbol": ce_sell["symbol"], "action": "SELL", "quantity": self.quantity},
                    {"symbol": pe_sell["symbol"], "action": "SELL", "quantity": self.quantity}
                ]
                entry_prices = [safe_float(ce_sell["ltp"]), safe_float(pe_sell["ltp"])]
                self.tracker.add_legs(short_legs, entry_prices, side="SELL")

                # Keep track of all legs for exiting
                self.all_open_legs = [
                    {"symbol": ce_buy["symbol"], "action": "BUY", "quantity": self.quantity},
                    {"symbol": pe_buy["symbol"], "action": "BUY", "quantity": self.quantity},
                    {"symbol": ce_sell["symbol"], "action": "SELL", "quantity": self.quantity},
                    {"symbol": pe_sell["symbol"], "action": "SELL", "quantity": self.quantity}
                ]
        except Exception as e:
            self.logger.error(f"Error placing entry order: {e}")

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

                # EOD Square-off check
                now = datetime.now()
                if now.time() >= dt_time(15, 15) and self.all_open_legs:
                    self._close_position("eod_squareoff")
                    time.sleep(self.sleep_seconds)
                    continue

                # Fetch Chain
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # 1. EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, _, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # 2. ENTRY LOGIC
                if not self.all_open_legs:
                    can_trade_now = self.can_trade()
                    straddle_premium = self.get_atm_straddle_premium(chain)

                    self.logger.debug(format_kv(spot=chain_resp.get("underlying_ltp", 0),
                                                premium=straddle_premium,
                                                can_trade=can_trade_now))

                    # Edge detection on combined condition
                    entry_condition = (straddle_premium > self.min_straddle_premium) and can_trade_now

                    if self.debouncer.edge("entry_signal", entry_condition):
                        self.execute_entry(chain)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    BestNiftyIronCondor().run()
