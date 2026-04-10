#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if straddle premium > 120, 40% SL, 50% TP, max hold 45m.
"""
import os
import sys
import time
from datetime import datetime, timezone, timedelta

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
sys.path.insert(0, strategies_dir)
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


# Configuration Section
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "12"))

SL_PCT = float(os.getenv("SL_PCT", "40"))
TP_PCT = float(os.getenv("TP_PCT", "50"))
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))

COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

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


class StrategyClass:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.limiter = TradeLimiter(max_per_day=MAX_ORDERS_PER_DAY, max_per_hour=MAX_ORDERS_PER_HOUR, cooldown_seconds=COOLDOWN_SECONDS)
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_check = 0
        self.ist = timezone(timedelta(hours=5, minutes=30))

        self.entered_today = False
        self.current_date = datetime.now(self.ist).date()

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > EXPIRY_REFRESH_SEC):
            try:
                res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
                if isinstance(res, dict) and res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        self.expiry = choose_nearest_expiry(dates)
                        self.last_expiry_check = now
                        self.logger.info(format_kv(event="expiry_updated", expiry=self.expiry))
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def get_atm_straddle_premium(self, chain):
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

    def find_leg_in_chain(self, chain, offset, option_type):
        for item in chain:
            opt_data = item.get(option_type.lower(), {})
            if opt_data.get("label") == offset:
                return opt_data
        return None

    def _close_position(self, chain, reason):
        self.logger.info(format_kv(event="trade", action="close", reason=reason))

        close_orders = []
        for leg in self.tracker.open_legs:
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            close_orders.append({
                "symbol": leg["symbol"],
                "action": close_action,
                "quantity": leg["quantity"],
                "product": leg.get("product", PRODUCT)
            })

        # Prioritize BUY to cover (close short legs) before SELL to close (close long legs) for margin efficiency
        close_orders.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        for order in close_orders:
            try:
                self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=order["symbol"],
                    action=order["action"],
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=order["product"],
                    quantity=order["quantity"],
                    position_size=0
                )
                self.logger.info(f"Trade response: Closed {order['symbol']} with {order['action']}")
            except Exception as e:
                self.logger.error(f"Error closing leg {order['symbol']}: {e}")

        self.tracker.clear()

    def can_trade(self, now_time):
        hour = now_time.hour
        minute = now_time.minute
        time_val = hour * 100 + minute

        if time_val < 1000:
            return False
        if time_val > 1515:
            return False

        if self.entered_today:
            return False

        if not self.limiter.allow():
            return False

        return True

    def run(self):
        self.logger.info(format_kv(event="strategy_start", name=STRATEGY_NAME))
        while True:
            try:
                now_dt = datetime.now(self.ist)

                # Check for new day
                if now_dt.date() > self.current_date:
                    self.current_date = now_dt.date()
                    self.entered_today = False
                    self.limiter = TradeLimiter(max_per_day=MAX_ORDERS_PER_DAY, max_per_hour=MAX_ORDERS_PER_HOUR, cooldown_seconds=COOLDOWN_SECONDS)

                if not is_market_open():
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                try:
                    chain_resp = self.client.optionchain(
                        underlying=UNDERLYING,
                        exchange=UNDERLYING_EXCHANGE,
                        expiry_date=self.expiry,
                        strike_count=STRIKE_COUNT
                    )
                except Exception as e:
                    self.logger.error(f"Optionchain API error: {e}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.debug(format_kv(event="invalid_chain", reason=reason))
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                spot = safe_float(chain_resp.get("underlying_ltp"))

                # Exits by 15:15
                time_val = now_dt.hour * 100 + now_dt.minute
                if time_val >= 1515 and self.tracker.open_legs:
                    self._close_position(chain, "eod_square_off")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade(now_dt):
                    straddle_premium = self.get_atm_straddle_premium(chain)

                    self.logger.debug(format_kv(spot=spot, straddle_premium=straddle_premium))

                    signal_cond = straddle_premium > 120
                    signal = self.debouncer.edge("iron_condor_entry", signal_cond)

                    if signal:
                        offsets = [
                            ("OTM4", "CE", "BUY"),
                            ("OTM4", "PE", "BUY"),
                            ("OTM2", "CE", "SELL"),
                            ("OTM2", "PE", "SELL")
                        ]

                        tracker_legs = []
                        entry_prices = []
                        api_legs = []

                        missing_leg = False
                        for offset, otype, action in offsets:
                            opt_data = self.find_leg_in_chain(chain, offset, otype)
                            if not opt_data:
                                self.logger.warning(f"Could not find {offset} {otype} in chain")
                                missing_leg = True
                                break

                            tracker_legs.append({
                                "symbol": opt_data["symbol"],
                                "action": action,
                                "quantity": QUANTITY,
                                "product": PRODUCT
                            })
                            entry_prices.append(float(opt_data["ltp"]))

                            api_legs.append({
                                "offset": offset,
                                "option_type": otype,
                                "action": action,
                                "quantity": QUANTITY,
                                "product": PRODUCT
                            })

                        if not missing_leg:
                            self.logger.info(format_kv(event="trade", action="entry", strategy="Iron_Condor"))
                            try:
                                response = self.client.optionsmultiorder(
                                    strategy=STRATEGY_NAME,
                                    underlying=UNDERLYING,
                                    exchange=UNDERLYING_EXCHANGE,
                                    expiry_date=self.expiry,
                                    legs=api_legs
                                )
                                self.logger.info(f"Trade response: {response}")

                                self.tracker.add_legs(tracker_legs, entry_prices, side="SELL")
                                self.limiter.record()
                                self.entered_today = True

                            except Exception as e:
                                self.logger.error(f"Error placing entry order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    StrategyClass().run()
