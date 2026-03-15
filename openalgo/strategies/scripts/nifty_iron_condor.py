#!/usr/bin/env python3
"""
NIFTY Iron Condor Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor entered after 10 AM if straddle premium > 120, holding max 45 mins.
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
        self.strategy_name = os.getenv("STRATEGY_NAME", "NIFTY_IC_10AM")
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
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "15"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=self.max_orders_per_day, max_per_hour=self.max_orders_per_hour, cooldown_seconds=self.cooldown_seconds)
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_fetch = 0
        self.entered_today = False
        self.last_trade_date = None
        self.all_open_legs = []

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_fetch) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res.get("status") == "success" and res.get("data"):
                    dates = res["data"]
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_fetch = now
                    self.logger.info(f"Selected Expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        now = datetime.now()

        # Reset daily entry flag
        if self.last_trade_date != now.date():
            self.entered_today = False
            self.last_trade_date = now.date()

        if self.entered_today:
            return False

        # Only after 10:00 AM
        if now.hour < 10:
            return False

        # Don't enter after 2:30 PM (to be safe before 3:15 PM EOD)
        if now.hour >= 15 or (now.hour == 14 and now.minute >= 30):
            return False

        return self.limiter.allow()

    def check_eod_exit(self):
        now = datetime.now()
        # Exit all positions by 3:15 PM
        if now.hour > 15 or (now.hour == 15 and now.minute >= 15):
            return True
        return False

    def _close_position(self, chain, reason):
        self.logger.info(f"Exiting position. Reason: {reason}")

        legs_to_close = self.all_open_legs if self.all_open_legs else self.tracker.open_legs

        for leg in legs_to_close:
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            try:
                res = self.client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg.get("quantity", self.quantity),
                    position_size=0
                )
                self.logger.info(f"Closed leg {leg['symbol']}: {res}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def _get_atm_straddle_premium(self, chain, atm_strike):
        for item in chain:
            if item.get("strike") == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp"))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp"))
                return ce_ltp + pe_ltp
        return 0.0

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} strategy...")
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")

                # EXIT MANAGEMENT FIRST (always check exits before entries)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if not exit_now and self.check_eod_exit():
                        exit_now = True
                        exit_reason = "eod_squareoff"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    straddle_premium = self._get_atm_straddle_premium(chain, atm_strike)

                    # Only logging every few cycles to not spam unless near threshold
                    if straddle_premium > 0:
                        self.logger.debug(format_kv(
                            time=datetime.now().strftime("%H:%M:%S"),
                            spot=chain_resp.get("underlying_ltp"),
                            straddle=straddle_premium,
                            req=self.min_straddle_premium
                        ))

                    if straddle_premium > self.min_straddle_premium:
                        self.logger.info(f"Signal met: Straddle premium ({straddle_premium}) > {self.min_straddle_premium}. Entering Iron Condor.")

                        # Place multi-leg order: Buy wings first, then Sell inner legs
                        legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        res = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=legs
                        )

                        self.logger.info(f"Trade response: {res}")

                        if res.get("status") == "success":
                            self.entered_today = True
                            self.limiter.record()

                            # Identify the specific symbols and LTPs to start tracking
                            otm2_ce, otm2_pe, otm4_ce, otm4_pe = None, None, None, None

                            for item in chain:
                                if item.get("ce", {}).get("label") == "OTM2": otm2_ce = item["ce"]
                                if item.get("pe", {}).get("label") == "OTM2": otm2_pe = item["pe"]
                                if item.get("ce", {}).get("label") == "OTM4": otm4_ce = item["ce"]
                                if item.get("pe", {}).get("label") == "OTM4": otm4_pe = item["pe"]

                            if otm2_ce and otm2_pe and otm4_ce and otm4_pe:
                                short_legs = [
                                    {"symbol": otm2_ce["symbol"], "action": "SELL", "quantity": self.quantity},
                                    {"symbol": otm2_pe["symbol"], "action": "SELL", "quantity": self.quantity}
                                ]
                                short_prices = [otm2_ce["ltp"], otm2_pe["ltp"]]

                                self.all_open_legs = [
                                    {"symbol": otm4_ce["symbol"], "action": "BUY", "quantity": self.quantity},
                                    {"symbol": otm4_pe["symbol"], "action": "BUY", "quantity": self.quantity},
                                    {"symbol": otm2_ce["symbol"], "action": "SELL", "quantity": self.quantity},
                                    {"symbol": otm2_pe["symbol"], "action": "SELL", "quantity": self.quantity}
                                ]

                                # Track only the short legs for profit/loss calculation to avoid premature exits
                                self.tracker.add_legs(short_legs, short_prices, side="SELL")
                                self.logger.info("Successfully added short legs to position tracker.")
                            else:
                                self.logger.warning("Could not identify all leg symbols from chain. Tracking may fail.")

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondor().run()
