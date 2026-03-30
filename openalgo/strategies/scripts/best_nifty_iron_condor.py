#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if straddle premium > 120, sells OTM2/buys OTM4, strict limits.
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


# Mandatory API Key Retrieval
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

        # Configuration Section
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_IC_WebUI")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Strategy-specific constraints
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))
        self.sl_pct = float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Rate Limiting & Sleep Config
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "15"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "300"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # State tracking
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

        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.current_date = datetime.now().date()

    def ensure_expiry(self):
        """Auto-resolve nearest expiry if none provided or it's time to refresh."""
        now = time.time()
        if (self.expiry is None) or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    expiries = res.get("data")
                    self.expiry = choose_nearest_expiry(expiries)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                else:
                    self.logger.warning("Could not fetch expiry dates.")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def get_atm_straddle_premium(self, chain):
        """Calculate the combined premium of the ATM CE and ATM PE."""
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" and pe.get("label") == "ATM":
                ce_ltp = safe_float(ce.get("ltp"))
                pe_ltp = safe_float(pe.get("ltp"))
                if ce_ltp > 0 and pe_ltp > 0:
                    return ce_ltp + pe_ltp
        return 0.0

    def get_legs_for_entry(self, chain):
        """Find the required legs: Sell OTM2, Buy OTM4"""
        legs_to_execute = []
        ce_otm2, pe_otm2 = None, None
        ce_otm4, pe_otm4 = None, None

        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})

            if ce.get("label") == "OTM2": ce_otm2 = ce
            if pe.get("label") == "OTM2": pe_otm2 = pe
            if ce.get("label") == "OTM4": ce_otm4 = ce
            if pe.get("label") == "OTM4": pe_otm4 = pe

        if ce_otm2 and pe_otm2 and ce_otm4 and pe_otm4:
            # Note: Options are defined in execution order. BUY first for margin benefit.
            legs_to_execute = [
                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
            ]

            entry_prices = {
                "OTM4_CE": safe_float(ce_otm4.get("ltp")),
                "OTM4_PE": safe_float(pe_otm4.get("ltp")),
                "OTM2_CE": safe_float(ce_otm2.get("ltp")),
                "OTM2_PE": safe_float(pe_otm2.get("ltp"))
            }
            return legs_to_execute, entry_prices
        return None, None

    def execute_entry(self, legs, entry_prices):
        try:
            self.logger.info(f"Placing Iron Condor Entry Orders: {legs}")
            response = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.options_exchange,
                expiry_date=self.expiry,
                legs=legs
            )
            self.logger.info(format_kv(event="trade", type="ENTRY", status=response.get("status", "unknown")))

            if response.get("status") == "success":
                self.tracker.add_legs(legs, entry_prices, side="SELL")
                self.limiter.record()
                self.entered_today = True
        except Exception as e:
            self.logger.error(f"Error placing entry order: {e}")

    def execute_exit(self, chain, reason):
        try:
            self.logger.info(f"Closing Iron Condor position due to {reason}.")
            legs_to_close = []

            # Reverse the open legs
            for leg in self.tracker.open_legs:
                close_action = "BUY" if leg["action"] == "SELL" else "SELL"
                legs_to_close.append({
                    "offset": leg["offset"],
                    "option_type": leg["option_type"],
                    "action": close_action,
                    "quantity": leg["quantity"],
                    "product": leg["product"]
                })

            # Place reverse BUY orders first for margin
            legs_to_close.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

            response = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.options_exchange,
                expiry_date=self.expiry,
                legs=legs_to_close
            )
            self.logger.info(format_kv(event="trade", type="EXIT", reason=reason, status=response.get("status", "unknown")))

            if response.get("status") == "success":
                self.tracker.clear()
        except Exception as e:
            self.logger.error(f"Error placing exit order: {e}")

    def check_eod_exit(self):
        """Force exit at 15:15 (3:15 PM) to avoid volatility."""
        now = datetime.now().time()
        if now.hour == 15 and now.minute >= 15:
            return True
        return False

    def check_entry_time(self):
        """Entry is only allowed after 10:00 AM and before 15:00 PM."""
        now = datetime.now().time()
        if now.hour > 10 or (now.hour == 10 and now.minute >= 0):
            if now.hour < 15:
                return True
        return False

    def can_trade(self):
        # Reset daily limit tracking
        now_date = datetime.now().date()
        if now_date != self.current_date:
            self.entered_today = False
            self.current_date = now_date

        return (not self.entered_today) and self.limiter.allow()

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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.debug(f"Invalid option chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0.0))

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    # Check manual EOD
                    if self.check_eod_exit():
                        self.execute_exit(chain, "eod_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    # Check typical SL/TP/Time logic
                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self.execute_exit(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS
                straddle_premium = self.get_atm_straddle_premium(chain)

                # PREPARE TO LOG
                self.logger.info(format_kv(
                    spot=underlying_ltp,
                    straddle=straddle_premium,
                    open_positions=len(self.tracker.open_legs)
                ))

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    # Evaluate time
                    time_ok = self.check_entry_time()
                    # Evaluate conditions
                    premium_ok = straddle_premium > self.min_straddle_premium

                    signal = self.debouncer.edge("entry_signal", time_ok and premium_ok)

                    if signal:
                        legs, prices = self.get_legs_for_entry(chain)
                        if legs and prices:
                            self.execute_entry(legs, prices)
                        else:
                            self.logger.warning("Entry conditions met, but could not resolve required offset legs in chain.")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    strategy = NiftyIronCondor()
    strategy.run()
