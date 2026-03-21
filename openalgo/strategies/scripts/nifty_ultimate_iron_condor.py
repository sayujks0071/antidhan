#!/usr/bin/env python3
"""
Nifty Ultimate Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle > 120, sells OTM2/buys OTM4, 40% SL, 50% TP, 45m max hold, exits by 3:15 PM.
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


class NiftyUltimateIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.logger.info("Initializing Nifty Ultimate Iron Condor Strategy...")

        self.strategy_name = os.getenv("STRATEGY_NAME", "NIFTY_ULTIMATE_IC")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "30"), 30)
        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "120"), 120)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)

        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"), 120.0)

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.last_trade_date = None

        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.all_open_legs = []

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success":
                    expiries = res.get("data", [])
                    if expiries:
                        self.expiry = choose_nearest_expiry(expiries)
                        self.last_expiry_refresh = now
                        self.logger.info(f"Resolved nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def get_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" and pe.get("label") == "ATM":
                ce_ltp = safe_float(ce.get("ltp"), 0.0)
                pe_ltp = safe_float(pe.get("ltp"), 0.0)
                if ce_ltp > 0 and pe_ltp > 0:
                    return ce_ltp + pe_ltp
        return 0.0

    def can_trade_now(self):
        now = datetime.now()

        if self.last_trade_date != now.date():
            self.entered_today = False
            self.last_trade_date = now.date()

        if self.entered_today:
            return False

        current_time = now.time()
        start_time = datetime.strptime("10:00:00", "%H:%M:%S").time()
        end_time = datetime.strptime("15:15:00", "%H:%M:%S").time()

        if current_time < start_time or current_time >= end_time:
            return False

        return self.limiter.allow()

    def should_eod_exit(self):
        now = datetime.now()
        eod_time = datetime.strptime("15:15:00", "%H:%M:%S").time()
        return now.time() >= eod_time

    def _close_position(self, reason):
        self.logger.info(f"Closing position. Reason: {reason}")

        for leg in self.all_open_legs:
            symbol = leg.get("symbol")
            if not symbol:
                continue

            action = "BUY" if leg.get("action") == "SELL" else "SELL"
            quantity = leg.get("quantity", self.quantity)

            try:
                self.logger.info(format_kv(event="trade", action=action, symbol=symbol, quantity=quantity, reason=reason))
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=quantity,
                    position_size=0
                )
                self.logger.info(f"Trade response: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {symbol}: {e}")

        self.tracker.clear()
        self.all_open_legs = []
        self.logger.info(format_kv(position_status="closed", exit_reason=reason))

    def _get_option_symbol(self, chain, offset, opt_type):
        for item in chain:
            opt = item.get(opt_type.lower(), {})
            if opt.get("label") == offset:
                return opt.get("symbol")
        return None

    def _get_option_ltp(self, chain, offset, opt_type):
        for item in chain:
            opt = item.get(opt_type.lower(), {})
            if opt.get("label") == offset:
                return safe_float(opt.get("ltp"), 0.0)
        return 0.0

    def run(self):
        self.logger.info("Starting Nifty Ultimate Iron Condor main loop")

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

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = safe_float(chain_resp.get("underlying_ltp"), 0.0)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                    if self.should_eod_exit():
                        self._close_position("eod_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade_now():
                    straddle_premium = self.get_straddle_premium(chain)
                    self.logger.debug(format_kv(spot=spot, straddle_premium=straddle_premium))

                    condition = straddle_premium > self.min_straddle_premium

                    if self.debouncer.edge("enter_ic", condition):
                        self.logger.info(f"Signal generated: Straddle premium {straddle_premium} > {self.min_straddle_premium}")

                        # Sells OTM2 CE and PE, buys OTM4 CE and PE for protection
                        legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        self.logger.info(format_kv(event="trade", action="multiorder", strategy="IronCondor"))

                        try:
                            resp = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.underlying_exchange,
                                expiry_date=self.expiry,
                                legs=legs
                            )
                            self.logger.info(f"Trade response: {resp}")

                            self.limiter.record()
                            self.entered_today = True

                            tracker_legs = []
                            self.all_open_legs = []

                            for leg in legs:
                                offset = leg["offset"]
                                opt_type = leg["option_type"]
                                action = leg["action"]

                                symbol = self._get_option_symbol(chain, offset, opt_type)
                                ltp = self._get_option_ltp(chain, offset, opt_type)

                                leg_info = {
                                    "symbol": symbol,
                                    "offset": offset,
                                    "option_type": opt_type,
                                    "action": action,
                                    "entry_price": ltp,
                                    "quantity": leg["quantity"]
                                }

                                self.all_open_legs.append(leg_info)

                                if action == "SELL" and symbol:
                                    tracker_legs.append({
                                        "symbol": symbol,
                                        "entry_price": ltp
                                    })

                            if tracker_legs:
                                self.tracker.add_legs(tracker_legs, [leg["entry_price"] for leg in tracker_legs], side="SELL")

                            self.logger.info(format_kv(position_status="opened", straddle_premium=straddle_premium))

                        except Exception as e:
                            self.logger.error(f"Error placing multi-leg order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyUltimateIronCondor().run()
