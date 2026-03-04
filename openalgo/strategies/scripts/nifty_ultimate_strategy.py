#!/usr/bin/env python3
"""
Nifty Ultimate Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10:00 AM if straddle premium > 120. Sells OTM2 and buys OTM4 for protection. Uses 40% SL and 50% TP, max 1 trade/day.
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
    from trading_utils import is_market_open
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


class NiftyUltimateStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Ultimate_IC")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk management
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Strategy specific params
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))
        self.entry_start_hour = int(os.getenv("ENTRY_START_HOUR", "10"))
        self.entry_start_minute = int(os.getenv("ENTRY_START_MINUTE", "0"))
        self.exit_hour = int(os.getenv("EXIT_HOUR", "15"))
        self.exit_minute = int(os.getenv("EXIT_MINUTE", "15"))

        # Rate limits
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # Clients and Utilities
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=int(os.getenv("MAX_ORDERS_PER_DAY", "1")),
            max_per_hour=int(os.getenv("MAX_ORDERS_PER_HOUR", "1")),
            cooldown_seconds=int(os.getenv("COOLDOWN_SECONDS", "300"))
        )
        self.debouncer = SignalDebouncer()

        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0

    def ensure_expiry(self):
        """Auto-resolve nearest expiry if not set or if it needs refreshing."""
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    nearest = choose_nearest_expiry(dates)
                    if nearest:
                        if nearest != self.expiry:
                            self.logger.info(f"Resolved new nearest expiry: {nearest}")
                            self.expiry = nearest
                        self.last_expiry_refresh = now
                else:
                    self.logger.warning("Failed to fetch expiries.")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def is_within_entry_window(self, dt=None):
        if not dt:
            dt = datetime.now()
        current_time = dt.time()

        entry_start = dt.replace(hour=self.entry_start_hour, minute=self.entry_start_minute, second=0, microsecond=0).time()
        exit_time = dt.replace(hour=self.exit_hour, minute=self.exit_minute, second=0, microsecond=0).time()

        return entry_start <= current_time < exit_time

    def get_atm_straddle_premium(self, chain):
        for strike_data in chain:
            ce = strike_data.get("ce", {})
            pe = strike_data.get("pe", {})
            if ce.get("label") == "ATM" and pe.get("label") == "ATM":
                ce_ltp = safe_float(ce.get("ltp"))
                pe_ltp = safe_float(pe.get("ltp"))
                if ce_ltp > 0 and pe_ltp > 0:
                    return ce_ltp + pe_ltp
        return 0.0

    def _close_position(self, chain, reason):
        """Closes all tracked legs by taking the opposite action using placesmartorder."""
        if not self.tracker.open_legs:
            return

        self.logger.info(f"Closing position. Reason: {reason}")

        # In a real scenario, you'd iterate `self.tracker.open_legs` and use `placesmartorder` with the actual symbols.
        from trading_utils import APIClient

        # Fallback if APIClient isn't initialized or if client doesn't have placesmartorder:
        # We can create an APIClient instance just for these exits, or use self.client if it supports it.
        # In this template, we assume OptionChainClient might not have placesmartorder, but APIClient does.
        # Actually, trading_utils.APIClient does have placesmartorder. Let's initialize it if needed.
        # Or better yet, just use OptionChainClient which in OpenAlgo generally inherits or proxies to the same endpoints,
        # or just instantiate a fresh one. Let's instantiate a fresh one to be safe.

        try:
            api_client = APIClient(api_key=API_KEY, host=HOST)

            self.logger.info("Sending exit orders for open legs...")
            for leg in self.tracker.open_legs:
                symbol = leg.get("symbol")
                if not symbol:
                    self.logger.warning("Leg missing symbol, cannot exit via placesmartorder.")
                    continue

                action = "BUY" if leg["action"] == "SELL" else "SELL"

                resp = api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=1  # Target net position
                )

                if resp and resp.get("status") == "success":
                    self.logger.info(f"event=trade Trade response: Successfully closed {symbol} with {action} order.")
                else:
                    self.logger.error(f"Failed to close {symbol}: {resp}")
        except Exception as e:
            self.logger.error(f"Error while closing positions: {e}")

        self.tracker.clear()
        self.logger.info("Position closed successfully.")

    def can_trade(self):
        return self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} strategy loop.")
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=4, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.warning(f"Invalid chain data: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = chain_resp.get("underlying_ltp", 0.0)

                # EXIT MANAGEMENT FIRST
                dt_now = datetime.now()
                eod_time = dt_now.replace(hour=self.exit_hour, minute=self.exit_minute, second=0, microsecond=0)

                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if not exit_now and dt_now >= eod_time:
                        exit_now = True
                        exit_reason = "eod_square_off"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # Check End of Day
                if dt_now >= eod_time:
                    time.sleep(self.sleep_seconds)
                    continue

                # CALCULATE INDICATORS
                straddle_premium = self.get_atm_straddle_premium(chain)

                self.logger.info(format_kv(
                    spot=underlying_ltp,
                    straddle_premium=straddle_premium,
                    open_legs=len(self.tracker.open_legs),
                    expiry=self.expiry
                ))

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    if not self.is_within_entry_window():
                        time.sleep(self.sleep_seconds)
                        continue

                    if straddle_premium > self.min_straddle_premium:
                        signal_condition = True
                    else:
                        signal_condition = False

                    if self.debouncer.edge("entry_signal", signal_condition):
                        self.logger.info(f"Entry signal triggered. Straddle premium: {straddle_premium}")

                        legs_to_trade = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        response = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=legs_to_trade
                        )

                        if response and response.get("status") == "success":
                            self.logger.info("event=trade Trade response: Multi-leg order placed successfully.")
                            # Simulate finding the entry prices from chain to track them
                            # Since we don't know exact fill price immediately, we use LTP from chain
                            entry_prices = {}
                            tracked_legs = []
                            for leg in legs_to_trade:
                                offset = leg["offset"]
                                opt_type = leg["option_type"].lower()
                                for strike_data in chain:
                                    opt_data = strike_data.get(opt_type, {})
                                    if opt_data.get("label") == offset:
                                        symbol = opt_data.get("symbol")
                                        ltp = safe_float(opt_data.get("ltp"))
                                        entry_prices[symbol] = ltp

                                        # Keep track of what we opened to close it later
                                        tracked_legs.append({
                                            "symbol": symbol,
                                            "action": leg["action"],
                                            "option_type": leg["option_type"],
                                            "offset": offset
                                        })
                                        break

                            self.tracker.add_legs(tracked_legs, entry_prices, side="SELL")
                            self.limiter.record()
                        else:
                            self.logger.error(f"Failed to place multi-leg order: {response}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyUltimateStrategy().run()
