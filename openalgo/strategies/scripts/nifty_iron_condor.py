#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120, sells OTM2/buys OTM4 with 40% SL, 50% TP, max 45m hold.
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


class NiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Strategy specific params
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))
        self.manual_expiry = os.getenv("EXPIRY_DATE", "")

        # Clients
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Position and state tracking
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.expiry = self.manual_expiry
        self.last_expiry_check = 0
        self.entered_today = False
        self.all_open_legs = []  # Maintain track of all open legs for exit

    def ensure_expiry(self):
        if self.manual_expiry:
            return

        now = time.time()
        if now - self.last_expiry_check > self.expiry_refresh_sec or not self.expiry:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_check = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                else:
                    self.logger.warning(f"Failed to fetch expiry dates: {res}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade_now(self):
        """Check if current time is within trading window and rules."""
        now = datetime.now()

        # Must be market open
        if not is_market_open():
            return False

        # Nifty specific timing
        # Enter after 10:00 AM
        if now.hour < 10:
            return False

        # Exit all positions and stop new entries before 3:15 PM (15:15)
        if now.hour > 15 or (now.hour == 15 and now.minute >= 15):
            return False

        # Only one trade per day
        if self.entered_today:
            return False

        return True

    def _close_position(self, chain, reason):
        """Closes all legs of the open position."""
        self.logger.info(format_kv(event="trade", action="EXIT", reason=reason, legs=len(self.all_open_legs)))

        # We need to reverse the side to close
        for leg in self.all_open_legs:
            try:
                action = "BUY" if leg["action"] == "SELL" else "SELL"
                # Use placesmartorder to close individual leg
                # But we don't have the exact option symbol unless we tracked it.
                # If OptionPositionTracker only tracks short legs, we must use self.all_open_legs which tracks full details

                symbol = leg.get("symbol")
                if not symbol:
                    self.logger.warning(f"Missing symbol for leg {leg}, cannot close individually.")
                    continue

                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg["quantity"],
                    position_size=0
                )
                self.logger.info(format_kv(event="trade", symbol=symbol, action=action, resp=resp))
            except Exception as e:
                self.logger.error(f"Error closing leg {leg}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def get_straddle_premium(self, chain_data, atm_strike):
        """Calculate ATM straddle premium."""
        for item in chain_data:
            if abs(float(item.get("strike", 0)) - atm_strike) < 0.1:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                return ce_ltp + pe_ltp
        return 0.0

    def find_leg_symbol_and_price(self, chain_data, offset, option_type):
        """Find the specific option symbol and LTP from the chain data based on offset and type."""
        for item in chain_data:
            opt_data = item.get(option_type.lower(), {})
            if opt_data.get("label") == offset:
                return opt_data.get("symbol"), safe_float(opt_data.get("ltp", 0.0))
        return None, 0.0

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} Strategy Loop")

        while True:
            try:
                # Reset daily flags at midnight
                now = datetime.now()
                if now.hour == 0 and now.minute == 0:
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid option chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")
                spot_price = safe_float(chain_resp.get("underlying_ltp", 0))

                # EXIT MANAGEMENT FIRST
                # Check for EOD Square-off
                if self.tracker.open_legs and (now.hour > 15 or (now.hour == 15 and now.minute >= 15)):
                    self._close_position(chain, "eod_square_off")
                    time.sleep(self.sleep_seconds)
                    continue

                # Check SL/TP/Time Stop via tracker
                if self.tracker.open_legs:
                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade_now() and self.limiter.allow():
                    straddle_premium = self.get_straddle_premium(chain, atm_strike)

                    self.logger.info(format_kv(spot=spot_price, straddle=straddle_premium, atm=atm_strike, time=now.strftime("%H:%M")))

                    condition = straddle_premium > self.min_straddle_premium
                    signal = self.debouncer.edge("iron_condor_entry", condition)

                    if signal:
                        self.logger.info(format_kv(event="signal", type="ENTRY", premium=straddle_premium))

                        # Execute Multi-leg order
                        legs_req = [
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
                            legs=legs_req
                        )

                        if resp and resp.get("status") == "success":
                            self.logger.info(format_kv(event="trade", action="ENTRY", status="success"))

                            short_legs = []
                            short_prices = []

                            # Gather symbols and prices from chain to track
                            for req in legs_req:
                                sym, price = self.find_leg_symbol_and_price(chain, req["offset"], req["option_type"])
                                if sym:
                                    leg_info = {
                                        "symbol": sym,
                                        "action": req["action"],
                                        "quantity": req["quantity"],
                                        "option_type": req["option_type"]
                                    }
                                    self.all_open_legs.append(leg_info)

                                    # Only track short legs for SL/TP in OptionPositionTracker
                                    if req["action"] == "SELL":
                                        short_legs.append(leg_info)
                                        short_prices.append(price)

                            if short_legs:
                                self.tracker.add_legs(short_legs, short_prices, side="SELL")

                            self.limiter.record()
                            self.entered_today = True
                        else:
                            self.logger.error(f"Failed to place multi-leg order: {resp}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondor().run()
