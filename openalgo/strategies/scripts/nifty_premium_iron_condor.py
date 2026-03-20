#!/usr/bin/env python3
"""
Nifty Premium Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if straddle premium > 120, holds 45 mins max.
"""
import os
import sys
import time
from datetime import datetime, timedelta

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


class NiftyPremiumIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Config via os.getenv
        self.strategy_name = os.getenv("STRATEGY_NAME", "PremiumIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"))
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))
        self.expiry_date = os.getenv("EXPIRY_DATE", "").strip()

        # State
        self.expiry = self.expiry_date
        self.last_expiry_check = 0
        self.entered_today = False
        self.current_date = datetime.now().date()

        # Trackers
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.all_open_legs = [] # Stores all legs to close later (including buys)

        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )

    def ensure_expiry(self):
        if self.expiry and (time.time() - self.last_expiry_check < self.expiry_refresh_sec):
            return

        try:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.last_expiry_check = time.time()
                    self.logger.info(f"Selected expiry: {self.expiry}")
        except Exception as e:
            self.logger.error(f"Expiry fetch error: {e}")

    def _close_position(self, exit_reason):
        if not self.all_open_legs:
            return

        self.logger.info(f"event=trade Closing position. Reason: {exit_reason}")

        for leg in self.all_open_legs:
            action = "BUY" if leg["action"] == "SELL" else "SELL"
            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg["quantity"],
                    position_size=0 # Full square off
                )
                self.logger.info(f"Trade response: Closed {leg['symbol']} - {resp}")
            except Exception as e:
                self.logger.error(f"Failed to close leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def can_trade(self):
        now = datetime.now().time()
        start_time = datetime.strptime("10:00", "%H:%M").time()
        end_time = datetime.strptime("14:30", "%H:%M").time()
        return start_time <= now <= end_time and self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name}...")

        while True:
            try:
                if datetime.now().date() != self.current_date:
                    self.entered_today = False
                    self.current_date = datetime.now().date()
                    self.limiter = TradeLimiter(
                        max_per_day=self.max_orders_per_day,
                        max_per_hour=self.max_orders_per_hour,
                        cooldown_seconds=self.cooldown_seconds
                    )

                try:
                    market_open = is_market_open()
                except:
                    market_open = True

                if not market_open:
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=10)
                if not valid:
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # Exit Management First
                now_time = datetime.now().time()
                eod_time = datetime.strptime("15:15", "%H:%M").time()

                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if now_time >= eod_time:
                        exit_now = True
                        exit_reason = "eod_squareoff"

                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue
                else:
                    # EOD cleanup if orphaned legs remain
                    if self.all_open_legs and now_time >= eod_time:
                        self._close_position("eod_squareoff")

                # Entry Logic
                if not self.all_open_legs and not self.entered_today:
                    if self.can_trade():
                        atm_ce = None
                        atm_pe = None
                        for item in chain:
                            if item.get("ce", {}).get("label") == "ATM":
                                atm_ce = safe_float(item.get("ce", {}).get("ltp"))
                                atm_pe = safe_float(item.get("pe", {}).get("ltp"))
                                break

                        if atm_ce is not None and atm_pe is not None:
                            straddle_premium = atm_ce + atm_pe
                            spot = safe_float(chain_resp.get("underlying_ltp"))

                            self.logger.info(format_kv(
                                spot=f"{spot:.2f}",
                                straddle=f"{straddle_premium:.2f}",
                                status="FLAT"
                            ))

                            condition = straddle_premium > 120.0

                            if self.debouncer.edge("iron_condor_entry", condition):
                                self.logger.info(f"event=trade Straddle premium > 120 ({straddle_premium:.2f}). Entering Iron Condor.")

                                legs = [
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
                                    legs=legs
                                )

                                self.logger.info(f"Trade response: {resp}")

                                if resp.get("status") == "success":
                                    self.entered_today = True
                                    self.limiter.record()

                                    # Find exact symbols and LTPs to add to tracker
                                    tracker_legs = []
                                    tracker_prices = []

                                    for req_leg in legs:
                                        offset = req_leg["offset"]
                                        opt_type = req_leg["option_type"].lower()
                                        action = req_leg["action"]

                                        sym = None
                                        ltp = 0.0

                                        for item in chain:
                                            opt = item.get(opt_type, {})
                                            if opt.get("label") == offset:
                                                sym = opt.get("symbol")
                                                ltp = safe_float(opt.get("ltp"))
                                                break

                                        if sym:
                                            resolved_leg = {
                                                "symbol": sym,
                                                "option_type": opt_type.upper(),
                                                "action": action,
                                                "quantity": self.quantity,
                                                "entry_price": ltp
                                            }
                                            self.all_open_legs.append(resolved_leg)

                                            # Only add short legs to tracker to avoid false positive SL hits
                                            if action == "SELL":
                                                tracker_legs.append(resolved_leg)
                                                tracker_prices.append(ltp)

                                    if tracker_legs:
                                        self.tracker.add_legs(tracker_legs, tracker_prices, side="SELL")

            except Exception as e:
                self.logger.error(f"Main loop error: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyPremiumIronCondor().run()
