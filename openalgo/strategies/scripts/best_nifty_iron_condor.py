#!/usr/bin/env python3
"""
Best Nifty Iron Condor Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Nifty Iron Condor after 10 AM if straddle premium > 120. Sells OTM2, Buys OTM4.
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
    """
    Nifty Iron Condor Strategy:
    - Enters after 10 AM when straddle premium is > 120
    - Sells OTM2 CE and PE, buys OTM4 CE and PE for protection
    - Uses 40% SL and 50% TP on the short legs
    - Maximum hold time of 45 minutes
    - Only one trade per day
    - Exits all positions by 3:15 PM
    """

    def __init__(self):
        self.logger = PrintLogger()

        # Strategy Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "Best_Nifty_Iron_Condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        # Risk Management Parameters
        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        # Timings Configuration
        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "300"), 300)
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "10"), 10)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)
        self.manual_expiry = os.getenv("EXPIRY_DATE", "")

        # API Clients
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Trackers and limiters
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

        # State Variables
        self.expiry = None
        self.last_expiry_check = 0
        self.entered_today = False
        self.all_open_legs = []  # Keeps track of all legs (including BUY legs) to close them properly

        self.logger.info(f"Initialized {self.strategy_name} - SL: {self.sl_pct}%, TP: {self.tp_pct}%, Max Hold: {self.max_hold_min}m")

    def ensure_expiry(self):
        """Fetches the nearest valid expiry if needed."""
        now = time.time()
        if self.expiry and (now - self.last_expiry_check < self.expiry_refresh_sec):
            return

        self.last_expiry_check = now

        if self.manual_expiry:
            self.expiry = normalize_expiry(self.manual_expiry)
            self.logger.info(f"Using manual expiry: {self.expiry}")
            return

        try:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res and res.get("status") == "success" and res.get("data"):
                self.expiry = choose_nearest_expiry(res.get("data"))
                self.logger.info(f"Auto-resolved nearest expiry: {self.expiry}")
            else:
                self.logger.warning(f"Failed to fetch expiry dates: {res}")
        except Exception as e:
            self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        """Checks if current time and state allow a new entry."""
        if self.entered_today:
            return False

        now = datetime.now()
        current_time = now.time()

        entry_start = datetime.strptime("10:00:00", "%H:%M:%S").time()
        entry_end = datetime.strptime("14:30:00", "%H:%M:%S").time()

        if not (entry_start <= current_time <= entry_end):
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        """Closes all legs of the Iron Condor individually using APIClient."""
        self.logger.info(format_kv(event="closing_position", reason=reason, total_legs=len(self.all_open_legs)))

        closed_count = 0
        for leg in self.all_open_legs:
            symbol = leg.get("symbol")
            original_action = leg.get("action")
            close_action = "BUY" if original_action == "SELL" else "SELL"

            self.logger.info(format_kv(event="close_leg", symbol=symbol, action=close_action))

            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0
                )
                if resp and resp.get("status") == "success":
                    closed_count += 1
                else:
                    self.logger.warning(f"Failed to close leg {symbol}: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {symbol}: {e}")

        self.logger.info(format_kv(event="position_closed", total_closed=closed_count, expected=len(self.all_open_legs)))

        self.tracker.clear()
        self.all_open_legs = []

    def run(self):
        """Main execution loop for the strategy."""
        self.logger.info(f"Starting {self.strategy_name} main loop...")

        while True:
            try:
                # EOD Reset
                now = datetime.now()
                if now.time() > datetime.strptime("15:30:00", "%H:%M:%S").time():
                    self.entered_today = False
                    self.limiter.reset_daily()

                # Market open check
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                # EOD Square-off
                if now.time() >= datetime.strptime("15:15:00", "%H:%M:%S").time():
                    if self.all_open_legs:
                        self.logger.info(format_kv(event="eod_square_off", time=str(now.time())))
                        self._close_position(chain=[], reason="eod_square_off")
                    time.sleep(self.sleep_seconds)
                    continue

                # Expiry resolution
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.debug(f"Chain not valid: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, _legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS (Straddle Premium)
                atm_strike = chain_resp.get("atm_strike")
                straddle_premium = 0.0

                for item in chain:
                    if item.get("strike") == atm_strike:
                        ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0.0))
                        pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0.0))
                        straddle_premium = ce_ltp + pe_ltp
                        break

                self.logger.debug(format_kv(spot=spot, premium=straddle_premium, atm=atm_strike))

                # ENTRY LOGIC
                signal_condition = straddle_premium > 120.0
                signal = self.debouncer.edge("iron_condor_entry", signal_condition and self.can_trade())

                if not self.tracker.open_legs and signal:
                    self.logger.info(format_kv(event="signal_detected", premium=straddle_premium, spot=spot))

                    legs_config = [
                        {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                        {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                        {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                    ]

                    self.logger.info("Placing Multi-leg Order...")
                    try:
                        order_resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.options_exchange,
                            expiry_date=self.expiry,
                            legs=legs_config
                        )

                        if order_resp and order_resp.get("status") == "success":
                            executed_legs = order_resp.get("data", [])
                            self.logger.info(format_kv(event="entry_success", legs_executed=len(executed_legs)))

                            short_legs = []
                            entry_prices = []

                            for leg in executed_legs:
                                # Save all legs to internal state for proper closing
                                self.all_open_legs.append({
                                    "symbol": leg.get("symbol"),
                                    "action": leg.get("action")
                                })

                                # Only add SELL legs to the tracker to monitor for SL/TP
                                if leg.get("action") == "SELL":
                                    short_legs.append(leg)
                                    entry_prices.append(leg.get("average_price", leg.get("price", 0.0)))

                            if short_legs:
                                self.tracker.add_legs(short_legs, entry_prices, side="SELL")

                            self.entered_today = True
                            self.limiter.record()
                        else:
                            self.logger.error(f"Order failed: {order_resp}")
                    except Exception as order_ex:
                        self.logger.error(f"Error placing order: {order_ex}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
