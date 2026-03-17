#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor entered after 10 AM when straddle premium > 120. Sells OTM2, buys OTM4.
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
    from trading_utils import APIClient, is_market_open
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

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.opt_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Strategy specific params
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Timing constraints
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))

        # Clients and Utilities
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=int(os.getenv("MAX_ORDERS_PER_DAY", "1")),
            max_per_hour=int(os.getenv("MAX_ORDERS_PER_HOUR", "1")),
            cooldown_seconds=self.cooldown_seconds
        )

        # State
        self.expiry = None
        self.last_expiry_check = 0
        self.entered_today = False
        self.all_open_legs = []

        self.logger.info(format_kv(
            msg="Strategy initialized",
            strategy=self.strategy_name,
            sl=f"{self.sl_pct}%",
            tp=f"{self.tp_pct}%",
            max_hold=f"{self.max_hold_min}m"
        ))

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            manual_expiry = os.getenv("EXPIRY_DATE")
            if manual_expiry:
                self.expiry = manual_expiry
                self.last_expiry_check = now
                self.logger.info(format_kv(msg="Using manual expiry", expiry=self.expiry))
                return

            try:
                res = self.client.expiry(self.underlying, self.opt_exchange, "options")
                if isinstance(res, dict) and res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        new_expiry = choose_nearest_expiry(dates)
                        if new_expiry != self.expiry:
                            self.expiry = new_expiry
                            self.logger.info(format_kv(msg="Updated expiry", expiry=self.expiry))
                        self.last_expiry_check = now
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def _get_option_data(self, chain, strike, opt_type):
        for item in chain:
            if abs(float(item.get("strike", 0)) - strike) < 0.1:
                return item.get(opt_type.lower(), {})
        return {}

    def get_straddle_premium(self, chain_resp):
        atm_strike = chain_resp.get("atm_strike")
        if not atm_strike:
            return 0.0

        chain = chain_resp.get("chain", [])
        ce_data = self._get_option_data(chain, atm_strike, "ce")
        pe_data = self._get_option_data(chain, atm_strike, "pe")

        ce_ltp = safe_float(ce_data.get("ltp"))
        pe_ltp = safe_float(pe_data.get("ltp"))
        return ce_ltp + pe_ltp

    def can_trade(self):
        now = datetime.now().time()

        # Start trading at 10:00 AM
        start_time = datetime.strptime("10:00:00", "%H:%M:%S").time()
        # No new entries after 2:30 PM (EOD square off is at 3:15 PM)
        end_time = datetime.strptime("14:30:00", "%H:%M:%S").time()

        if now < start_time or now > end_time:
            return False

        if self.entered_today:
            return False

        return self.limiter.allow()

    def check_eod_squareoff(self):
        now = datetime.now().time()
        squareoff_time = datetime.strptime("15:15:00", "%H:%M:%S").time()
        if now >= squareoff_time and self.all_open_legs:
            return True
        return False

    def _close_position(self, exit_reason):
        self.logger.info(format_kv(msg="Closing position", reason=exit_reason))

        for leg in self.all_open_legs:
            try:
                # Reverse the action
                close_action = "BUY" if leg["action"] == "SELL" else "SELL"

                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.opt_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg["quantity"],
                    position_size=0
                )
                self.logger.info(format_kv(
                    event="trade",
                    msg="Leg closed",
                    symbol=leg["symbol"],
                    action=close_action,
                    response=resp.get("status", "unknown") if isinstance(resp, dict) else "unknown"
                ))
            except Exception as e:
                self.logger.error(f"Error closing leg {leg.get('symbol')}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def execute_entry(self, chain):
        self.logger.info(format_kv(msg="Executing Iron Condor entry"))

        # BUY legs ordered before SELL legs for margin efficiency
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
                exchange=self.exchange,
                expiry_date=self.expiry,
                legs=legs
            )

            self.logger.info(f"Trade response: {response}")

            if isinstance(response, dict) and response.get("status") == "success":
                data = response.get("data", [])
                if not data:
                    self.logger.warning("No data in response, tracking failed.")
                    return

                self.limiter.record()
                self.entered_today = True
                self.all_open_legs = []
                short_legs = []
                entry_prices = []

                for leg_resp in data:
                    action = leg_resp.get("action", "")
                    symbol = leg_resp.get("symbol", "")
                    entry_price = safe_float(leg_resp.get("price"))

                    leg_record = {
                        "symbol": symbol,
                        "action": action,
                        "quantity": self.quantity
                    }
                    self.all_open_legs.append(leg_record)

                    if action == "SELL":
                        short_legs.append(leg_record)
                        entry_prices.append(entry_price)
                        self.logger.info(format_kv(
                            event="trade",
                            msg="Short leg filled",
                            symbol=symbol,
                            price=entry_price
                        ))

                # Track only short legs for SL/TP
                if short_legs and entry_prices:
                    self.tracker.add_legs(short_legs, entry_prices, side="SELL")

        except Exception as e:
            self.logger.error(f"Error placing entry order: {e}")

    def run(self):
        while True:
            try:
                # Reset daily flags on new day (very simplified, usually need more robust date tracking)
                # But simple enough for a stateless script that runs Mon-Fri via scheduler

                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # 1. EOD Square-off check
                if self.check_eod_squareoff():
                    self._close_position("EOD Square-off")
                    time.sleep(self.sleep_seconds)
                    continue

                # 2. SL/TP/Time Stop Exit Management
                if self.all_open_legs and self.tracker.open_legs:
                    exit_now, _, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # 3. Entry Logic
                if not self.all_open_legs and self.can_trade():
                    straddle_premium = self.get_straddle_premium(chain_resp)
                    spot = safe_float(chain_resp.get("underlying_ltp"))

                    self.logger.info(format_kv(
                        spot=spot,
                        premium=straddle_premium,
                        msg="Checking entry condition"
                    ))

                    cond = straddle_premium > self.min_straddle_premium

                    if self.debouncer.edge("ic_entry", cond):
                        self.execute_entry(chain)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyIronCondor().run()
filepath: openalgo/strategies/scripts/nifty_iron_condor.py
