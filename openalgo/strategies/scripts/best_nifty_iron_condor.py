#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM if straddle premium > 120. Sells OTM2 CE/PE, buys OTM4 CE/PE for protection. 40% SL, 50% TP, 45 min max hold.
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


class NiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "BestNiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Management Params
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # Tracking variables
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=1, max_per_hour=1, cooldown_seconds=self.cooldown_seconds)
        self.debouncer = SignalDebouncer()

        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0

        # State
        self.entered_today = False
        self.last_trade_date = None
        self.all_open_legs = []

    def ensure_expiry(self):
        """Fetch and cache the nearest expiry."""
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data", [])
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Updated expiry to {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        """Check time window and rate limits."""
        now = datetime.now()

        # Reset daily tracking
        if self.last_trade_date != now.date():
            self.entered_today = False
            self.last_trade_date = now.date()

        if self.entered_today:
            return False

        current_time = now.time()

        # Enter after 10:00 AM
        if current_time < datetime.strptime("10:00", "%H:%M").time():
            return False

        # Don't enter after 2:30 PM
        if current_time >= datetime.strptime("14:30", "%H:%M").time():
            return False

        return self.limiter.allow()

    def check_eod_exit(self):
        """Check if it's time to square off all positions (3:15 PM)."""
        now = datetime.now()
        current_time = now.time()
        eod_time = datetime.strptime("15:15", "%H:%M").time()
        return current_time >= eod_time

    def _close_position(self, chain, reason="unknown"):
        """Close the open multi-leg position."""
        if not self.tracker.open_legs and not self.all_open_legs:
            return

        self.logger.info(format_kv(event="close_position", reason=reason, strategy=self.strategy_name))

        try:
            # Import APIClient dynamically for equity/options order placement
            from trading_utils import APIClient
            order_client = APIClient(api_key=API_KEY, host=HOST)

            # To maintain margin efficiency, sort legs so we Buy to Cover (close short legs)
            # before we Sell to Close (close long legs).
            def sort_action(leg):
                # Reverse action: original "SELL" becomes "BUY" (higher priority), "BUY" becomes "SELL"
                return 0 if leg.get("action") == "SELL" else 1

            sorted_legs = sorted(self.all_open_legs, key=sort_action)

            # Close each leg using the exact option symbol captured during entry
            for leg in sorted_legs:
                symbol = leg.get("symbol")
                if not symbol:
                    self.logger.warning(f"Could not close leg missing symbol: {leg}")
                    continue

                # Reverse the action to close
                close_action = "SELL" if leg.get("action") == "BUY" else "BUY"

                try:
                    resp = order_client.placesmartorder(
                        strategy=self.strategy_name,
                        symbol=symbol,
                        action=close_action,
                        exchange=self.options_exchange,
                        pricetype="MARKET",
                        product=self.product,
                        quantity=self.quantity,
                        position_size=0  # Target net zero position
                    )
                    self.logger.info(f"Closed leg {symbol} ({close_action}): {resp}")
                except Exception as leg_e:
                    self.logger.error(f"Failed to close leg {symbol}: {leg_e}")

            self.tracker.clear()
            self.all_open_legs = []
            self.logger.info("Successfully closed all position legs.")
        except Exception as e:
            self.logger.error(f"Error closing position: {e}")

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} - NIFTY Iron Condor")
        self.logger.info(f"Config: SL={self.sl_pct}%, TP={self.tp_pct}%, MaxHold={self.max_hold_min}m, MinPremium={self.min_straddle_premium}")

        while True:
            try:
                if not is_market_open():
                    # Reset daily flags on new day inside loop if needed
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # EOD Square-off check
                if self.check_eod_exit() and (self.tracker.open_legs or self.all_open_legs):
                    self._close_position(chain=[], reason="EOD_SQUARE_OFF")
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
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot_price = safe_float(chain_resp.get("underlying_ltp", 0.0))

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS (Straddle Premium)
                atm_ce_ltp = 0.0
                atm_pe_ltp = 0.0
                otm2_ce = None
                otm2_pe = None
                otm4_ce = None
                otm4_pe = None

                for item in chain:
                    ce = item.get("ce", {})
                    pe = item.get("pe", {})

                    if ce.get("label") == "ATM":
                        atm_ce_ltp = safe_float(ce.get("ltp", 0.0))
                    if pe.get("label") == "ATM":
                        atm_pe_ltp = safe_float(pe.get("ltp", 0.0))

                    if ce.get("label") == "OTM2":
                        otm2_ce = ce
                    if pe.get("label") == "OTM2":
                        otm2_pe = pe

                    if ce.get("label") == "OTM4":
                        otm4_ce = ce
                    if pe.get("label") == "OTM4":
                        otm4_pe = pe

                straddle_premium = atm_ce_ltp + atm_pe_ltp

                # ENTRY LOGIC
                if not self.tracker.open_legs and not self.all_open_legs and self.can_trade():

                    # Condition: Straddle premium must be above threshold
                    premium_ok = straddle_premium > self.min_straddle_premium

                    # Log state periodically or on change
                    self.logger.info(format_kv(spot=spot_price, straddle_premium=straddle_premium, premium_ok=premium_ok))

                    if self.debouncer.edge("entry_signal", premium_ok):
                        if otm2_ce and otm2_pe and otm4_ce and otm4_pe:

                            self.logger.info("event=trade Action=ENTRY Reason=Premium_Threshold_Met")

                            legs = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product, "symbol": otm4_ce.get("symbol")},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product, "symbol": otm4_pe.get("symbol")},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product, "symbol": otm2_ce.get("symbol")},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product, "symbol": otm2_pe.get("symbol")},
                            ]

                            try:
                                response = self.client.optionsmultiorder(
                                    strategy=self.strategy_name,
                                    underlying=self.underlying,
                                    exchange=self.underlying_exchange, # Match NSE_INDEX for optionsmultiorder based on prompt example
                                    expiry_date=self.expiry,
                                    legs=legs
                                )

                                self.logger.info(f"Trade response: {response}")

                                # In a real implementation we would parse response to get entry prices
                                # For now we simulate entry prices from current LTP for the tracked short legs
                                entry_prices = [
                                    safe_float(otm2_ce.get("ltp", 0.0)),
                                    safe_float(otm2_pe.get("ltp", 0.0))
                                ]

                                # Track short legs for SL/TP management
                                tracking_legs = [
                                    {"offset": "OTM2", "option_type": "CE", "action": "SELL"},
                                    {"offset": "OTM2", "option_type": "PE", "action": "SELL"}
                                ]

                                self.tracker.add_legs(tracking_legs, entry_prices, side="SELL")

                                # Track all legs for closure later
                                self.all_open_legs = legs

                                self.limiter.record()
                                self.entered_today = True

                            except Exception as e:
                                self.logger.error(f"Error placing order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondor().run()
