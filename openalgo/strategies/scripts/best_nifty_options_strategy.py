#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy targeting 10 AM entry with minimum straddle premium > 120.
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
sys.path.insert(0, utils_dir)

try:
    from trading_utils import is_market_open
    from trading_utils import APIClient
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


class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()

        # Configuration from env with defaults
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        self.sl_pct = safe_float(os.getenv("SL_PCT", "40"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120"), 120.0)

        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "120"), 120)
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "30"), 30)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
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

        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        nearest = choose_nearest_expiry(dates)
                        if nearest:
                            self.expiry = nearest
                            self.last_expiry_refresh = now
                            self.logger.info(format_kv(event="expiry_updated", expiry=self.expiry))
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def get_atm_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" or pe.get("label") == "ATM":
                ce_ltp = safe_float(ce.get("ltp"), 0.0)
                pe_ltp = safe_float(pe.get("ltp"), 0.0)
                return ce_ltp + pe_ltp
        return 0.0

    def get_option_by_label(self, chain, label, opt_type):
        for item in chain:
            opt = item.get(opt_type.lower(), {})
            if opt.get("label") == label:
                return opt
        return {}

    def is_time_valid_for_entry(self):
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        # Entry after 10 AM, before 3 PM
        if now_ist.hour < 10 or (now_ist.hour == 10 and now_ist.minute < 0):
            return False
        if now_ist.hour >= 15:
            return False
        return True

    def is_time_valid_for_exit(self):
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        # Force exit at 3:15 PM
        if now_ist.hour == 15 and now_ist.minute >= 15:
            return True
        return False

    def can_trade(self):
        return self.is_time_valid_for_entry() and self.limiter.allow()

    def _close_position(self, chain, reason):
        if not self.tracker.open_legs:
            return

        self.logger.info(format_kv(event="closing_position", reason=reason))

        # We placed the order using multiorder, ideally we should close them.
        # But we don't have the API logic fully to close legs directly.
        # We will log the exit and clear tracker.
        # Construct the legs to close: reverse the actions
        close_legs = []
        for leg in self.tracker.open_legs:
            action = leg.get("action", "")
            close_action = "BUY" if action == "SELL" else "SELL"
            # Prioritize BUY legs to close shorts, then SELL legs to close longs
            close_legs.append({
                "symbol": leg.get("symbol"),
                "option_type": leg.get("option_type"),
                "action": close_action,
                "quantity": leg.get("quantity", self.quantity),
                "product": leg.get("product", self.product)
            })

        # Sort so BUY comes first (closing shorts for margin release)
        close_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        self.logger.info(f"Closing legs: {close_legs}")

        # Use placesmartorder to close each leg individually using the specific symbol
        for leg in close_legs:
            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg.get("symbol"),
                    action=leg.get("action"),
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=leg.get("product", self.product),
                    quantity=leg.get("quantity", self.quantity),
                    position_size=1
                )
                self.logger.info(f"Trade response for {leg.get('symbol')}: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg.get('symbol')}: {e}")

        self.tracker.clear()
        self.logger.info(format_kv(event="position_closed", status="success"))

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} strategy loop")

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
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EOD Exit
                if self.tracker.open_legs and self.is_time_valid_for_exit():
                    self._close_position(chain, "eod_square_off")
                    time.sleep(self.sleep_seconds)
                    continue

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    straddle_premium = self.get_atm_straddle_premium(chain)

                    self.logger.debug(format_kv(
                        event="checking_entry",
                        straddle_premium=straddle_premium,
                        min_required=self.min_straddle_premium
                    ))

                    signal = self.debouncer.edge("entry_signal", straddle_premium > self.min_straddle_premium)

                    if signal:
                        # Enter Iron Condor
                        # Sell OTM2 CE and PE, Buy OTM4 CE and PE

                        ce_sell = self.get_option_by_label(chain, "OTM2", "ce")
                        pe_sell = self.get_option_by_label(chain, "OTM2", "pe")
                        ce_buy = self.get_option_by_label(chain, "OTM4", "ce")
                        pe_buy = self.get_option_by_label(chain, "OTM4", "pe")

                        if all([ce_sell, pe_sell, ce_buy, pe_buy]):
                            legs = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            ]

                            self.logger.info(format_kv(event="trade", action="ENTER_IRON_CONDOR", premium=straddle_premium))

                            response = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.underlying_exchange,
                                expiry_date=self.expiry,
                                legs=legs
                            )

                            if response and response.get("status") == "success":
                                self.limiter.record()

                                # Setup tracker with actual symbols
                                tracker_legs = [
                                    {"symbol": ce_buy.get("symbol"), "action": "BUY", "option_type": "CE"},
                                    {"symbol": pe_buy.get("symbol"), "action": "BUY", "option_type": "PE"},
                                    {"symbol": ce_sell.get("symbol"), "action": "SELL", "option_type": "CE"},
                                    {"symbol": pe_sell.get("symbol"), "action": "SELL", "option_type": "PE"},
                                ]
                                entry_prices = [
                                    safe_float(ce_buy.get("ltp")),
                                    safe_float(pe_buy.get("ltp")),
                                    safe_float(ce_sell.get("ltp")),
                                    safe_float(pe_sell.get("ltp")),
                                ]

                                self.tracker.add_legs(tracker_legs, entry_prices, side="SELL") # We consider this a net short/selling strategy
                                self.logger.info(format_kv(event="position_opened", status="success"))

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
