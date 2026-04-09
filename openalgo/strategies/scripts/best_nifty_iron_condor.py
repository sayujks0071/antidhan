#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if ATM straddle premium > 120, sells OTM2, buys OTM4.
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

        # Strategy Parameters
        self.strategy_name = os.getenv("STRATEGY_NAME", "NIFTY_IRON_CONDOR")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "20"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))
        self.manual_expiry = os.getenv("EXPIRY_DATE")

        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_check = 0
        self.entered_today = False

    def ensure_expiry(self):
        now = time.time()

        if self.manual_expiry:
            if not self.expiry:
                self.expiry = normalize_expiry(self.manual_expiry)
                self.last_expiry_check = now
                self.logger.info(format_kv(event="expiry_manual_override", expiry=self.expiry))
            return

        if not self.expiry or (now - self.last_expiry_check) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    expirations = res.get("data")
                    self.expiry = choose_nearest_expiry(expirations)
                    self.last_expiry_check = now
                    self.logger.info(format_kv(event="expiry_resolved", expiry=self.expiry))
                else:
                    self.logger.warning("Could not fetch expiry dates.")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        now_dt = datetime.now()

        # Don't trade if already entered today
        if self.entered_today:
            return False

        # Entry Time Filter: After 10:00 AM, Before 2:30 PM (14:30)
        current_time = now_dt.time()
        start_time = current_time.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = current_time.replace(hour=14, minute=30, second=0, microsecond=0)

        if not (start_time <= current_time <= end_time):
            return False

        return self.limiter.allow()

    def check_eod_exit(self):
        now_time = datetime.now().time()
        eod_time = now_time.replace(hour=15, minute=15, second=0, microsecond=0)
        return now_time >= eod_time

    def get_atm_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM":
                return safe_float(ce.get("ltp")) + safe_float(pe.get("ltp"))
        return 0.0

    def get_leg_by_label(self, chain, label, option_type):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == label:
                return opt
        return None

    def _close_position(self, chain, reason):
        if not self.tracker.open_legs:
            return

        self.logger.info(format_kv(event="exit_signal", reason=reason))

        closing_orders = []
        for leg in self.tracker.open_legs:
            symbol = leg.get("symbol")
            if not symbol:
                opt = self.get_leg_by_label(chain, leg.get("offset"), leg.get("option_type"))
                if opt:
                    symbol = opt.get("symbol")

            if symbol:
                action = "BUY" if leg.get("action") == "SELL" else "SELL"
                closing_orders.append({
                    "symbol": symbol,
                    "action": action,
                    "quantity": leg.get("quantity", self.quantity)
                })

        # Sort so BUY comes before SELL for margin efficiency
        closing_orders.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        for order in closing_orders:
            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=order["symbol"],
                    action=order["action"],
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=order["quantity"],
                    position_size=0  # Close
                )
                self.logger.info(format_kv(
                    event="trade",
                    type="close_leg",
                    symbol=order["symbol"],
                    action=order["action"],
                    status="success"
                ))
            except Exception as e:
                self.logger.error(f"Error closing leg {order['symbol']}: {e}")

        self.tracker.clear()

    def run(self):
        self.logger.info(format_kv(event="strategy_started", name=self.strategy_name))

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
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.warning(format_kv(event="invalid_chain", reason=reason))
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    if self.check_eod_exit():
                        self._close_position(chain, "eod_squareoff")
                    else:
                        exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                        if exit_now:
                            self._close_position(chain, exit_reason)

                    time.sleep(self.sleep_seconds)
                    continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    premium = self.get_atm_straddle_premium(chain)

                    premium_ok = premium >= self.min_straddle_premium
                    signal = self.debouncer.edge("iron_condor_entry", premium_ok)

                    if signal:
                            otm4_ce = self.get_leg_by_label(chain, "OTM4", "CE")
                            otm4_pe = self.get_leg_by_label(chain, "OTM4", "PE")
                            otm2_ce = self.get_leg_by_label(chain, "OTM2", "CE")
                            otm2_pe = self.get_leg_by_label(chain, "OTM2", "PE")

                            if all([otm4_ce, otm4_pe, otm2_ce, otm2_pe]):
                                legs = [
                                    {
                                        "offset": "OTM4", "option_type": "CE", "action": "BUY",
                                        "quantity": self.quantity, "product": self.product,
                                        "symbol": otm4_ce.get("symbol")
                                    },
                                    {
                                        "offset": "OTM4", "option_type": "PE", "action": "BUY",
                                        "quantity": self.quantity, "product": self.product,
                                        "symbol": otm4_pe.get("symbol")
                                    },
                                    {
                                        "offset": "OTM2", "option_type": "CE", "action": "SELL",
                                        "quantity": self.quantity, "product": self.product,
                                        "symbol": otm2_ce.get("symbol")
                                    },
                                    {
                                        "offset": "OTM2", "option_type": "PE", "action": "SELL",
                                        "quantity": self.quantity, "product": self.product,
                                        "symbol": otm2_pe.get("symbol")
                                    }
                                ]

                                try:
                                    response = self.client.optionsmultiorder(
                                        strategy=self.strategy_name,
                                        underlying=self.underlying,
                                        exchange=self.underlying_exchange,
                                        expiry_date=self.expiry,
                                        legs=legs
                                    )

                                    entry_prices = [
                                        safe_float(otm4_ce.get("ltp")),
                                        safe_float(otm4_pe.get("ltp")),
                                        safe_float(otm2_ce.get("ltp")),
                                        safe_float(otm2_pe.get("ltp"))
                                    ]

                                    self.tracker.add_legs(legs, entry_prices, side="SELL")
                                    self.limiter.record()
                                    self.entered_today = True

                                    self.logger.info(format_kv(
                                        event="trade",
                                        type="entry",
                                        premium=premium,
                                        status="success"
                                    ))
                                except Exception as e:
                                    self.logger.error(f"Error placing entry order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
