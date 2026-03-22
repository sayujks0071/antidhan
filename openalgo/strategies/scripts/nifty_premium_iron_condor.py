#!/usr/bin/env python3
"""
Nifty Premium Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if ATM straddle premium > 120. Sells OTM2, Buys OTM4.
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
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

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

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyPremiumIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        # Risk Parameters
        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        # Premium/Entry Filters
        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"), 120.0)

        # Rate Limiting
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)
        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "120"), 120)
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "10"), 10)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)

        # Clients and Utils
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
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

        # State
        self.expiry = os.getenv("EXPIRY_DATE", "")
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.current_date = datetime.now().date()
        self.all_open_legs = []

    def ensure_expiry(self):
        """Auto-resolve nearest expiry if not set or if it's time to refresh."""
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    expiries = res.get("data")
                    self.expiry = choose_nearest_expiry(expiries)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def _reset_daily_state_if_needed(self):
        today = datetime.now().date()
        if today != self.current_date:
            self.current_date = today
            self.entered_today = False
            self.logger.info("Reset daily tracking state.")

    def can_trade_now(self):
        """Check time-based filters."""
        now = datetime.now().time()

        # Don't trade before 10:00 AM
        start_time = datetime.strptime("10:00", "%H:%M").time()
        if now < start_time:
            return False

        # Don't enter after 2:30 PM (or generally close to 3:15 PM EOD)
        end_time = datetime.strptime("14:30", "%H:%M").time()
        if now > end_time:
            return False

        return True

    def should_eod_squareoff(self):
        """Check if it's time for EOD square-off (3:15 PM)."""
        now = datetime.now().time()
        eod_time = datetime.strptime("15:15", "%H:%M").time()
        return now >= eod_time

    def get_atm_straddle_premium(self, chain, atm_strike):
        """Calculate the sum of ATM CE and PE prices."""
        atm_ce_ltp = 0.0
        atm_pe_ltp = 0.0

        for item in chain:
            if abs(item.get("strike", 0) - atm_strike) < 0.1: # float comparison
                ce = item.get("ce", {})
                pe = item.get("pe", {})
                if ce and pe:
                    atm_ce_ltp = safe_float(ce.get("ltp", 0.0))
                    atm_pe_ltp = safe_float(pe.get("ltp", 0.0))
                break

        return atm_ce_ltp + atm_pe_ltp

    def _close_position(self, chain, reason):
        """Close all open legs."""
        self.logger.info(f"event=trade Closing position. Reason: {reason}")

        from trading_utils import APIClient
        api_client = APIClient(api_key=API_KEY, host=HOST)

        for leg in self.all_open_legs:
            # Reverse the action to close
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            symbol = leg["symbol"]

            try:
                resp = api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg["quantity"],
                    position_size=0
                )
                self.logger.info(f"Trade response: Closed {symbol} ({close_action}): {resp}")
            except Exception as e:
                self.logger.error(f"Failed to close leg {symbol}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} for {self.underlying}...")

        while True:
            try:
                self._reset_daily_state_if_needed()

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
                    self.logger.warning(f"Invalid chain data: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = safe_float(chain_resp.get("atm_strike", 0.0))
                spot = safe_float(chain_resp.get("underlying_ltp", 0.0))

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                    if self.should_eod_squareoff():
                        self._close_position(chain, "EOD_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    # Still in position, nothing else to do this loop
                    time.sleep(self.sleep_seconds)
                    continue

                # EOD check before evaluating entry
                if self.should_eod_squareoff():
                    time.sleep(self.sleep_seconds)
                    continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and not self.entered_today:

                    if not self.can_trade_now():
                        time.sleep(self.sleep_seconds)
                        continue

                    straddle_premium = self.get_atm_straddle_premium(chain, atm_strike)
                    self.logger.debug(format_kv(spot=spot, atm_strike=atm_strike, straddle=straddle_premium))

                    premium_ok = straddle_premium > self.min_straddle_premium

                    # Use debouncer combined with time check
                    signal = self.debouncer.edge("enter_ic", premium_ok and self.can_trade_now())

                    if signal:
                        if self.limiter.allow():
                            self.logger.info(f"Entry signal detected! Straddle: {straddle_premium} > {self.min_straddle_premium}")

                            # Build the Iron Condor
                            # Sells OTM2 CE and PE, buys OTM4 CE and PE
                            legs = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            ]

                            try:
                                response = self.client.optionsmultiorder(
                                    strategy=self.strategy_name,
                                    underlying=self.underlying,
                                    exchange=self.underlying_exchange,
                                    expiry_date=self.expiry,
                                    legs=legs
                                )

                                self.logger.info(f"event=trade Trade response: Multi-order placed: {response}")

                                if response and response.get("status") == "success":
                                    self.limiter.record()
                                    self.entered_today = True

                                    # Extract executed legs from the response
                                    executed_legs = response.get("data", [])
                                    if executed_legs:
                                        self.all_open_legs = executed_legs

                                        # Only track short legs for SL/TP management
                                        short_legs = [leg for leg in executed_legs if leg.get("action") == "SELL"]

                                        # Extract entry prices and add to tracker
                                        entry_prices = {leg["symbol"]: safe_float(leg.get("average_price", 0.0)) for leg in short_legs}
                                        self.tracker.add_legs(short_legs, entry_prices, side="SELL")
                                        self.logger.info(f"Position opened. Tracking {len(short_legs)} short legs.")
                                    else:
                                        self.logger.warning("Order succeeded but no legs returned in data.")

                            except Exception as e:
                                self.logger.error(f"Error placing multi-leg order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyPremiumIronCondor().run()
