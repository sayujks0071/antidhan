#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy for NIFTY options entering after 10 AM if ATM straddle > 120.
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

class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))
        self.manual_expiry = os.getenv("EXPIRY_DATE", "")

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
        self.entered_today = False
        self.last_trade_date = None
        self.protective_legs = []

    def ensure_expiry(self):
        now = time.time()
        if self.manual_expiry:
            self.expiry = self.manual_expiry
            return

        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res.get("status") == "success" and res.get("data"):
                    dates = res["data"]
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error resolving expiry: {e}")

    def get_atm_straddle_premium(self, chain, atm_strike):
        for item in chain:
            if item.get("strike") == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                return ce_ltp + pe_ltp
        return 0.0

    def get_option_by_offset(self, chain, offset, option_type):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset:
                return opt
        return None

    def _close_position(self, chain, exit_reason):
        if not self.tracker.open_legs and not self.protective_legs:
            return

        self.logger.info(f"Closing position. Reason: {exit_reason}")

        all_legs_to_close = list(self.tracker.open_legs)
        if self.protective_legs:
            all_legs_to_close.extend(self.protective_legs)

        for leg in all_legs_to_close:
            symbol = leg["symbol"]
            # Reverse action
            close_action = "BUY" if leg["side"] == "SELL" else "SELL"

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
                self.logger.info(format_kv(event="close_leg", symbol=symbol, action=close_action, response=str(resp)))
            except Exception as e:
                self.logger.error(f"Error closing leg {symbol}: {e}")

        self.tracker.clear()
        self.protective_legs = []

    def can_trade(self):
        now = datetime.now()

        # Reset daily tracking
        if self.last_trade_date != now.date():
            self.entered_today = False
            self.last_trade_date = now.date()

        if self.entered_today:
            return False

        # Time filter: Enters after 10 AM, exits all positions by 3:15 PM
        current_time = now.time()
        start_time = datetime.strptime("10:00:00", "%H:%M:%S").time()
        end_time = datetime.strptime("15:00:00", "%H:%M:%S").time()

        if current_time < start_time or current_time > end_time:
            return False

        return self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} Strategy")

        while True:
            try:
                now = datetime.now()

                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # Fetch option chain
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")
                spot_price = chain_resp.get("underlying_ltp", 0.0)

                # EXIT MANAGEMENT FIRST
                # EOD Square-off by 3:15 PM
                current_time = now.time()
                square_off_time = datetime.strptime("15:15:00", "%H:%M:%S").time()

                if self.tracker.open_legs or self.protective_legs:
                    if current_time >= square_off_time:
                        self._close_position(chain, "eod_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs_to_exit, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    straddle_premium = self.get_atm_straddle_premium(chain, atm_strike)
                    self.logger.info(format_kv(spot=spot_price, atm=atm_strike, straddle=straddle_premium))

                    if straddle_premium > 120.0:
                        otm2_ce = self.get_option_by_offset(chain, "OTM2", "CE")
                        otm2_pe = self.get_option_by_offset(chain, "OTM2", "PE")
                        otm4_ce = self.get_option_by_offset(chain, "OTM4", "CE")
                        otm4_pe = self.get_option_by_offset(chain, "OTM4", "PE")

                        if all([otm2_ce, otm2_pe, otm4_ce, otm4_pe]):
                            self.logger.info("Entry conditions met. Placing Iron Condor order.")

                            # BUY legs execute first, then SELL legs (margin efficiency)
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
                                self.logger.info(format_kv(event="trade", type="IronCondor", response=str(response)))

                                short_legs = [
                                    {"symbol": otm2_ce["symbol"], "side": "SELL", "entry_price": safe_float(otm2_ce["ltp"]), "qty": self.quantity},
                                    {"symbol": otm2_pe["symbol"], "side": "SELL", "entry_price": safe_float(otm2_pe["ltp"]), "qty": self.quantity}
                                ]
                                long_legs = [
                                    {"symbol": otm4_ce["symbol"], "side": "BUY", "entry_price": safe_float(otm4_ce["ltp"]), "qty": self.quantity},
                                    {"symbol": otm4_pe["symbol"], "side": "BUY", "entry_price": safe_float(otm4_pe["ltp"]), "qty": self.quantity}
                                ]

                                # We track only SHORT legs for SL/TP triggers
                                self.tracker.add_legs(short_legs, [leg["entry_price"] for leg in short_legs], side="SELL")
                                self.protective_legs = long_legs

                                self.entered_today = True
                                self.limiter.record()

                            except Exception as e:
                                self.logger.error(f"Error placing order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
