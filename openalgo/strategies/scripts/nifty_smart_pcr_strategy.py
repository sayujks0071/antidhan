#!/usr/bin/env python3
"""
Nifty Smart PCR Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Monitors Put-Call OI ratio across 12 strikes to buy ATM CE or PE directionally.
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


class NiftyPCRDirectionalStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.logger.info("Initializing Nifty Smart PCR Strategy...")

        # Configuration Section
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_PCR_Directional")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Strategy specific parameters
        self.bullish_pcr_threshold = float(os.getenv("BULLISH_PCR", "1.3"))
        self.bearish_pcr_threshold = float(os.getenv("BEARISH_PCR", "0.7"))

        # 0.5% and 0.8% typically translate to TP/SL of premium 50/80% in options trading context
        # based on standard platform defaults in configuration cheat sheet.
        # Using 50 and 80 percent respectively.
        self.sl_pct = float(os.getenv("SL_PCT", "50"))
        self.tp_pct = float(os.getenv("TP_PCT", "80"))

        # Time Management
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "30")) # Will set to 30 as it's a buying strategy standard
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "20")) # Sleep 20 seconds between checks
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "60"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # Risk Management
        max_orders_day = int(os.getenv("MAX_ORDERS_PER_DAY", "15"))
        max_orders_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "3"))

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=max_orders_day,
            max_per_hour=max_orders_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_check = 0

    def ensure_expiry(self):
        """Auto-resolve nearest expiry via API"""
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        # Find nearest expiry
                        nearest = choose_nearest_expiry(dates)
                        if nearest:
                            if self.expiry != nearest:
                                self.logger.info(f"Updated expiry to {nearest}")
                            self.expiry = nearest
                            self.last_expiry_check = now
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry: {e}")

    def can_trade(self):
        """Additional time-based constraints for entry"""
        now = datetime.now()
        # Don't enter before 9:30 AM
        if now.hour == 9 and now.minute < 30:
            return False
        # Don't enter after 3:15 PM
        if now.hour == 15 and now.minute >= 15:
            return False
        return self.limiter.allow()

    def _close_position(self, chain, reason):
        """Exits all open positions"""
        self.logger.info(f"event=exit reason={reason}")
        if not self.tracker.open_legs:
            return

        exit_legs = []
        for leg in self.tracker.open_legs:
            # Create an offsetting leg (reverse the action)
            exit_leg = leg.copy()
            exit_leg["action"] = "SELL" if leg["action"] == "BUY" else "BUY"
            exit_legs.append(exit_leg)

        try:
            response = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.options_exchange,
                expiry_date=self.expiry,
                legs=exit_legs
            )
            self.logger.info(f"Exit trade response: {response}")
        except Exception as e:
            self.logger.error(f"Failed to execute exit trade: {e}")

        # Clear the tracker after attempting to close
        self.tracker.clear()

    def execute_trade(self, chain, side):
        """Executes a buy order for ATM CE or PE"""
        atm_strike = None
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM" or item.get("pe", {}).get("label") == "ATM":
                atm_strike = item.get("strike")
                break

        if not atm_strike:
            self.logger.error("Could not find ATM strike in chain.")
            return

        option_type = "CE" if side == "BULLISH" else "PE"

        # Find entry price
        entry_price = 0.0
        for item in chain:
            if item.get("strike") == atm_strike:
                opt = item.get(option_type.lower(), {})
                entry_price = safe_float(opt.get("ltp"))
                break

        if entry_price <= 0:
            self.logger.error(f"Invalid entry price {entry_price} for {option_type}")
            return

        # Record trade intent
        self.limiter.record()

        legs = [
            {"offset": "ATM", "option_type": option_type, "action": "BUY", "quantity": self.quantity, "product": self.product}
        ]

        self.logger.info(format_kv(
            event="trade",
            action="BUY",
            type=option_type,
            strike=atm_strike,
            price=entry_price
        ))

        try:
            response = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.options_exchange,
                expiry_date=self.expiry,
                legs=legs
            )
            self.logger.info(f"Trade response: {response}")

            # Start tracking
            self.tracker.add_legs(legs, [entry_price], side="BUY")
        except Exception as e:
            self.logger.error(f"Failed to execute trade: {e}")

    def run(self):
        self.logger.info("Starting Strategy Main Loop...")
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
                    exchange=self.underlying_exchange, # usually NSE_INDEX for quotes
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=self.strike_count, require_oi=True)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Square-off before 3:15 PM
                    now = datetime.now()
                    if now.hour == 15 and now.minute >= 15:
                        exit_now = True
                        exit_reason = "eod_square_off"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS (PCR)
                total_ce_oi = 0
                total_pe_oi = 0

                for item in chain:
                    ce_oi = safe_int(item.get("ce", {}).get("oi", 0))
                    pe_oi = safe_int(item.get("pe", {}).get("oi", 0))
                    total_ce_oi += ce_oi
                    total_pe_oi += pe_oi

                pcr = 0.0
                if total_ce_oi > 0:
                    pcr = round(total_pe_oi / total_ce_oi, 2)

                self.logger.info(format_kv(spot=spot, pcr=pcr, status="monitoring"))

                # ENTRY LOGIC
                if not self.tracker.open_legs:
                    bullish_signal = pcr > self.bullish_pcr_threshold
                    bearish_signal = pcr < self.bearish_pcr_threshold

                    is_bullish = self.debouncer.edge("bullish", bullish_signal)
                    is_bearish = self.debouncer.edge("bearish", bearish_signal)

                    if (is_bullish or is_bearish) and self.can_trade():
                        side = "BULLISH" if is_bullish else "BEARISH"
                        self.execute_trade(chain, side)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    strategy = NiftyPCRDirectionalStrategy()
    strategy.run()
