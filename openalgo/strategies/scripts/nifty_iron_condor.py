#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy entering after 10 AM when straddle premium > 120. Sells OTM2, Buys OTM4.
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
        safe_int
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
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Management Config
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Strategy Specific Config
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))
        self.sell_offset = "OTM2"
        self.buy_offset = "OTM4"

        # Timing Config
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # State
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=1, max_per_hour=1, cooldown_seconds=self.cooldown_seconds)
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_check = 0

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check) > self.expiry_refresh_sec:
            try:
                manual_expiry = os.getenv("EXPIRY_DATE")
                if manual_expiry:
                    self.expiry = normalize_expiry(manual_expiry)
                else:
                    res = self.client.expiry(self.underlying, self.options_exchange, "options")
                    if res.get("status") == "success":
                        dates = res.get("data", [])
                        self.expiry = choose_nearest_expiry(dates)
                self.last_expiry_check = now
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        now = datetime.now()

        # Check time: 10:00 AM to 3:15 PM
        if now.hour < 10 or (now.hour == 15 and now.minute >= 15):
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        if not self.tracker.open_legs:
            return

        self.logger.info(format_kv(event="closing_position", reason=reason, legs=len(self.tracker.open_legs)))

        # We must close by specific symbol to avoid offset mismatch as ATM strike moves
        for leg in self.tracker.open_legs:
            if not leg.get("symbol"):
                continue

            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            resp = self.client.placesmartorder(
                strategy=self.strategy_name,
                symbol=leg["symbol"],
                action=close_action,
                exchange=self.options_exchange,
                pricetype="MARKET",
                product=self.product,
                quantity=leg.get("quantity", self.quantity),
                position_size=0
            )
            self.logger.info(format_kv(event="close_leg_response", symbol=leg["symbol"], action=close_action, status=resp.get("status"), message=resp.get("message")))

        self.tracker.clear()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name}...")
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
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # Check EOD square-off
                now = datetime.now()
                is_eod = (now.hour == 15 and now.minute >= 15)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    if is_eod:
                        self._close_position(chain, "eod_squareoff")
                    else:
                        exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                        if exit_now:
                            self._close_position(chain, exit_reason)
                            time.sleep(self.sleep_seconds)
                            continue

                if is_eod:
                    time.sleep(self.sleep_seconds)
                    continue

                # CALCULATE INDICATORS
                atm_strike = chain_resp.get("atm_strike")
                if not atm_strike:
                    for item in chain:
                        if item.get("ce", {}).get("label") == "ATM":
                            atm_strike = item["strike"]
                            break

                if atm_strike:
                    straddle_premium = 0.0
                    for item in chain:
                        if item["strike"] == atm_strike:
                            ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                            pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                            straddle_premium = ce_ltp + pe_ltp
                            break

                    self.logger.debug(format_kv(spot=chain_resp.get("underlying_ltp"), atm=atm_strike, premium=straddle_premium))

                    # ENTRY LOGIC
                    if not self.tracker.open_legs and self.can_trade():
                        # Condition: straddle premium > 120
                        if straddle_premium > self.min_straddle_premium:
                            self.logger.info(format_kv(event="entry_signal", premium=straddle_premium, atm=atm_strike))

                            # Place Iron Condor
                            # Sell OTM2 CE and PE, Buy OTM4 CE and PE
                            # Buy legs execute first
                            legs = [
                                {"offset": self.buy_offset, "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": self.buy_offset, "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": self.sell_offset, "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": self.sell_offset, "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            ]

                            resp = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.options_exchange,
                                expiry_date=self.expiry,
                                legs=legs
                            )

                            self.logger.info(format_kv(event="trade_response", status=resp.get("status"), message=resp.get("message")))

                            if resp.get("status") == "success":
                                self.limiter.record()
                                # Get entry prices if returned, else fallback
                                entry_prices = []
                                for leg in legs:
                                    leg_ltp = 0.0
                                    for item in chain:
                                        if item.get("ce", {}).get("label") == leg["offset"] and leg["option_type"] == "CE":
                                            leg_ltp = safe_float(item.get("ce", {}).get("ltp"))
                                            leg["symbol"] = item.get("ce", {}).get("symbol", "")
                                            break
                                        if item.get("pe", {}).get("label") == leg["offset"] and leg["option_type"] == "PE":
                                            leg_ltp = safe_float(item.get("pe", {}).get("ltp"))
                                            leg["symbol"] = item.get("pe", {}).get("symbol", "")
                                            break
                                    entry_prices.append(leg_ltp)

                                self.tracker.add_legs(legs, entry_prices, side="SELL")

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyIronCondor().run()
