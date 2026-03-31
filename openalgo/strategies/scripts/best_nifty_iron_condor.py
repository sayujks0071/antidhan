#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if straddle premium > 120. Sells OTM2, Buys OTM4.
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

class BestNiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.logger.info("Initializing Best Nifty Iron Condor Strategy...")

        # Configuration Parameters
        self.strategy_name = os.getenv("STRATEGY_NAME", "BestNiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "10"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Clients and Utilities
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )

        # State
        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.reset_date = datetime.now().date()
        self.all_open_legs = []

    def ensure_expiry(self):
        """Fetch and cache nearest expiry."""
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res.get("status") == "success" and "data" in res:
                    self.expiry = choose_nearest_expiry(res["data"])
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved Expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def _check_daily_reset(self):
        now_date = datetime.now().date()
        if now_date != self.reset_date:
            self.entered_today = False
            self.reset_date = now_date

    def can_trade(self):
        self._check_daily_reset()
        if self.entered_today:
            return False
        if not self.limiter.allow():
            return False
        return True

    def _close_position(self, chain, reason):
        """Closes all legs individually for correct multi-leg closure without relative offsets."""
        self.logger.info(f"Closing position. Reason: {reason}")

        if not self.all_open_legs:
            self.tracker.clear()
            return

        # Create map of LTPs to log the exit values
        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        # We use a separate API client for single-leg smart orders
        api_client = APIClient(api_key=API_KEY, host=HOST)

        # Priority: Close short legs (Buy to cover) before long legs (Sell to close) to maintain margin
        self.all_open_legs.sort(key=lambda leg: 1 if leg["action"] == "SELL" else 2)

        for leg in self.all_open_legs:
            symbol = leg["symbol"]
            entry_action = leg["action"].upper()
            exit_action = "BUY" if entry_action == "SELL" else "SELL"
            qty = leg["quantity"]

            curr_price = ltp_map.get(symbol, "UNKNOWN")

            try:
                resp = api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=exit_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=qty,
                    position_size=0  # Target net position is 0
                )
                self.logger.info(f"event=trade action=CLOSE_LEG symbol={symbol} req_action={exit_action} curr_price={curr_price} response={resp}")
            except Exception as e:
                self.logger.error(f"Failed to close leg {symbol}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def run(self):
        self.logger.info("Starting Main Event Loop.")

        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # Fetch Option Chain
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=self.strike_count, require_oi=True, require_volume=True)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                atm_strike = None
                for item in chain:
                    if item.get("ce", {}).get("label") == "ATM":
                        atm_strike = item.get("strike")
                        break

                # Check for EOD Exit logic (3:15 PM = 15:15)
                now = datetime.now()
                is_eod = now.hour > 15 or (now.hour == 15 and now.minute >= 15)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if is_eod:
                        exit_now = True
                        exit_reason = "eod_square_off"

                    if exit_now:
                        self.logger.info(format_kv(event="exit_triggered", reason=exit_reason))
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    # Time filter: Entry >= 10:00 AM
                    if now.hour < 10:
                        time.sleep(self.sleep_seconds)
                        continue

                    # Stop entry near EOD (prevent entry after 2:30 PM)
                    if now.hour >= 14 and now.minute >= 30:
                        time.sleep(self.sleep_seconds)
                        continue

                    straddle_premium = 0.0
                    if atm_strike is not None:
                        for item in chain:
                            if item.get("strike") == atm_strike:
                                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                                straddle_premium = ce_ltp + pe_ltp
                                break

                    # Premium filter condition
                    condition = straddle_premium > self.min_straddle_premium

                    if condition:
                        self.logger.info(format_kv(event="entry_signal", straddle=straddle_premium, min_straddle=self.min_straddle_premium))
                        self.limiter.record()
                        self.entered_today = True

                        # Define Iron Condor Legs
                        # Buy OTM4 CE, Buy OTM4 PE, Sell OTM2 CE, Sell OTM2 PE

                        # Place Multi-Leg Order (BUY legs before SELL legs for margin efficiency)
                        legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=legs
                        )

                        self.logger.info(f"event=trade action=OPEN_IRON_CONDOR response={resp}")

                        # Extract entry prices from the chain matching offsets
                        entry_prices = []
                        all_legs_data = []
                        for leg in legs:
                            offset = leg["offset"]
                            opt_type = leg["option_type"].lower()

                            # Find the matching option in the chain
                            price = 0.0
                            symbol = ""
                            for item in chain:
                                opt = item.get(opt_type, {})
                                if opt.get("label") == offset:
                                    price = safe_float(opt.get("ltp"))
                                    symbol = opt.get("symbol")
                                    break

                            entry_prices.append(price)

                            # Build the full leg info for tracker
                            leg_data = leg.copy()
                            leg_data["symbol"] = symbol
                            leg_data["entry_price"] = price
                            all_legs_data.append(leg_data)

                        # Extract entry prices and add to tracker (track all legs)
                        tracker_legs = []
                        tracker_prices = []
                        for leg_data in all_legs_data:
                            # We track all legs, so OptionPositionTracker knows how to compute net premium
                            tracker_legs.append(leg_data)
                            tracker_prices.append(leg_data["entry_price"])

                        # Add to Tracker
                        self.all_open_legs = all_legs_data.copy()
                        self.tracker.add_legs(tracker_legs, tracker_prices, side="SELL")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    BestNiftyIronCondorStrategy().run()
