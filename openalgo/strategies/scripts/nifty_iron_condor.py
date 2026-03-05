#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if straddle premium > 120. Sells OTM2, buys OTM4.
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


class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
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
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "20"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.min_premium = float(os.getenv("MIN_PREMIUM", "120"))

        self.manual_expiry = os.getenv("EXPIRY_DATE", None)

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

        self.expiry = None
        self.last_expiry_refresh = 0

    def ensure_expiry(self):
        now = time.time()
        if self.expiry and (now - self.last_expiry_refresh) < self.expiry_refresh_sec:
            return

        if self.manual_expiry:
            self.expiry = normalize_expiry(self.manual_expiry)
            self.last_expiry_refresh = now
            self.logger.info(f"Using manual expiry: {self.expiry}")
            return

        res = self.client.expiry(self.underlying, self.options_exchange, "options")
        if res and res.get("status") == "success" and res.get("data"):
            expiries = res.get("data")
            self.expiry = choose_nearest_expiry(expiries)
            self.last_expiry_refresh = now
            self.logger.info(f"Resolved nearest expiry: {self.expiry}")
        else:
            self.logger.error("Failed to fetch expiries.")

    def can_trade(self):
        now = datetime.now()
        # Only trade between 10:00 AM and 2:30 PM (leaving 45 mins before 3:15 PM EOD)
        if now.hour < 10:
            return False
        if now.hour > 14 or (now.hour == 14 and now.minute > 30):
            return False
        return self.limiter.allow()

    def is_eod(self):
        now = datetime.now()
        # EOD Square-off before 3:15 PM
        return now.hour >= 15 and now.minute >= 15

    def _close_position(self, chain, reason):
        self.logger.info(format_kv(event="trade", action="EXIT", reason=reason))

        # Determine offsetting legs for the exit
        # We had: BUY OTM4 CE, BUY OTM4 PE, SELL OTM2 CE, SELL OTM2 PE
        # To close: SELL OTM4 CE, SELL OTM4 PE, BUY OTM2 CE, BUY OTM2 PE
        # Wait, the prompt says "BUY legs execute first, then SELL legs (for margin efficiency)"
        # This applies to closing as well: buy back the short legs first, then sell the long wings.

        exit_legs = [
            {"offset": "OTM2", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM2", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM4", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM4", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
        ]

        response = self.client.optionsmultiorder(
            strategy=self.strategy_name,
            underlying=self.underlying,
            exchange=self.underlying_exchange,
            expiry_date=self.expiry,
            legs=exit_legs
        )

        if response and response.get("status") == "success":
            self.logger.info(f"Trade response: Exit successful. {response}")
            self.tracker.clear()
        else:
            self.logger.error(f"Trade response: Exit failed. {response}")
            # Do not clear tracker, retry on next loop

    def run(self):
        self.logger.info(f"Starting NiftyIronCondor strategy for {self.underlying}")
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
                    self.logger.debug(f"Invalid chain data: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                if not chain:
                    time.sleep(self.sleep_seconds)
                    continue

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    if self.is_eod():
                        self._close_position(chain, "eod_squareoff")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS (Straddle Premium)
                atm_ce_ltp = 0.0
                atm_pe_ltp = 0.0

                for item in chain:
                    ce = item.get("ce", {})
                    pe = item.get("pe", {})
                    if ce.get("label") == "ATM":
                        atm_ce_ltp = safe_float(ce.get("ltp"))
                    if pe.get("label") == "ATM":
                        atm_pe_ltp = safe_float(pe.get("ltp"))

                straddle_premium = atm_ce_ltp + atm_pe_ltp

                spot = chain_resp.get("underlying_ltp", 0.0)

                self.logger.debug(format_kv(spot=spot, atm_ce=atm_ce_ltp, atm_pe=atm_pe_ltp, straddle=straddle_premium))

                # ENTRY LOGIC
                signal_condition = straddle_premium >= self.min_premium and self.can_trade()

                # Use debouncer to prevent rapid firing
                if self.debouncer.edge("enter_ic", signal_condition):
                    if not self.tracker.open_legs:
                        self.logger.info(format_kv(event="trade", action="ENTRY", reason="straddle_premium_high", straddle=straddle_premium))

                        entry_legs = [
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
                            legs=entry_legs
                        )

                        if response and response.get("status") == "success":
                            self.logger.info(f"Trade response: Entry successful. {response}")
                            self.limiter.record()

                            # Calculate entry prices to track
                            # We need to approximate entry prices from current chain LTPs
                            entry_prices = []
                            for leg in entry_legs:
                                offset = leg["offset"]
                                opt_type = leg["option_type"]
                                price = 0.0
                                for item in chain:
                                    opt_data = item.get(opt_type.lower(), {})
                                    if opt_data.get("label") == offset:
                                        price = safe_float(opt_data.get("ltp"))
                                        break
                                entry_prices.append(price)

                            self.tracker.add_legs(entry_legs, entry_prices, side="SELL")
                        else:
                            self.logger.error(f"Trade response: Entry failed. {response}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
