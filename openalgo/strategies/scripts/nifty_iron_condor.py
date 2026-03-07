#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM if straddle > 120. Sells OTM2, Buys OTM4. SL 40%, TP 50%. Max hold 45 min.
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

        # Configuration Section
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Strategy Specific params
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))
        self.sell_offset = "OTM2"
        self.buy_offset = "OTM4"

        self.sl_pct = float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # State
        self.expiry = None
        self.last_expiry_fetch = 0
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        # Track whether we entered today
        self.entered_today = False
        self.current_date = datetime.now().date()

    def ensure_expiry(self):
        now = time.time()
        # Reset entered_today flag on a new day
        today = datetime.now().date()
        if today != self.current_date:
            self.entered_today = False
            self.current_date = today

        if not self.expiry or (now - self.last_expiry_fetch > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res["data"]
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_fetch = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                else:
                    self.logger.warning("Could not fetch expiry dates.")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        now = datetime.now()

        # Check time bounds: don't enter before 10 AM, stop entering before 3 PM
        if now.hour < 10 or (now.hour >= 15):
            return False

        # Stop new entries if already traded today
        if self.entered_today:
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        if not self.tracker.open_legs:
            return

        self.logger.info(f"Closing position. Reason: {reason}")

        close_legs = []
        # Reverse the legs to close out
        for leg in getattr(self, "all_ic_legs", self.tracker.open_legs):
            # We track the actual API symbols that were returned if possible,
            # but optionsmultiorder accepts offsets. If the platform needs precise symbols
            # we should build legs with symbols, but the boilerplate says:
            # "The 'offset' property can be used directly instead of manually resolving specific option symbols."

            # Note: For optionsmultiorder closing, we need to pass the same offset and option_type,
            # but reversing the action.

            close_leg = {
                "offset": leg["offset"],
                "option_type": leg["option_type"],
                "action": "BUY" if leg["action"] == "SELL" else "SELL",
                "quantity": leg["quantity"],
                "product": leg["product"]
            }
            close_legs.append(close_leg)

        # BUY legs execute first for margin efficiency
        close_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            resp = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.options_exchange,
                expiry_date=self.expiry,
                legs=close_legs
            )
            self.logger.info(f"Trade response: {resp}")
        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

        self.tracker.clear()
        self.all_ic_legs = []

    def run(self):
        self.logger.info("Starting Nifty Iron Condor Strategy...")
        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # EOD Square-off check (3:15 PM)
                now = datetime.now()
                if now.hour == 15 and now.minute >= 15:
                    if self.tracker.open_legs:
                        # Attempt exit but pass empty chain if necessary, reason is EOD
                        self._close_position([], "EOD Square-off")
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange, # NIFTY index usually NSE_INDEX
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")

                if not atm_strike:
                    for item in chain:
                        if item.get("ce", {}).get("label") == "ATM":
                            atm_strike = item["strike"]
                            break

                straddle_premium = 0.0
                for item in chain:
                    if item.get("ce", {}).get("label") == "ATM" and item.get("pe", {}).get("label") == "ATM":
                        straddle_premium = safe_float(item.get("ce", {}).get("ltp")) + safe_float(item.get("pe", {}).get("ltp"))
                        break

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    # Check straddle premium
                    if straddle_premium > self.min_straddle_premium:
                        # Construct legs
                        # Buy OTM4, Sell OTM2
                        legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        self.logger.info(format_kv(
                            event="trade",
                            action="ENTRY",
                            spot=chain_resp.get("underlying_ltp", atm_strike),
                            straddle=straddle_premium,
                            message="Entering Iron Condor"
                        ))

                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.options_exchange,
                            expiry_date=self.expiry,
                            legs=legs
                        )
                        self.logger.info(f"Trade response: {resp}")
                        self.limiter.record()
                        self.entered_today = True

                        # We need to find the entry prices of the sold legs to track SL/TP
                        # Using OptionPositionTracker on short legs only for strict SL/TP
                        # Find OTM2 legs in chain
                        entry_prices = []
                        tracked_legs = []

                        otm2_ce_ltp = 0
                        otm2_pe_ltp = 0

                        for item in chain:
                            if item.get("ce", {}).get("label") == "OTM2":
                                otm2_ce_ltp = safe_float(item.get("ce", {}).get("ltp"))
                                tracked_legs.append({
                                    "symbol": item["ce"]["symbol"],
                                    "action": "SELL",
                                    "quantity": self.quantity,
                                    "offset": "OTM2",
                                    "option_type": "CE",
                                    "product": self.product
                                })
                                entry_prices.append(otm2_ce_ltp)
                            elif item.get("pe", {}).get("label") == "OTM2":
                                otm2_pe_ltp = safe_float(item.get("pe", {}).get("ltp"))
                                tracked_legs.append({
                                    "symbol": item["pe"]["symbol"],
                                    "action": "SELL",
                                    "quantity": self.quantity,
                                    "offset": "OTM2",
                                    "option_type": "PE",
                                    "product": self.product
                                })
                                entry_prices.append(otm2_pe_ltp)

                            # Need to store the buy legs as well so _close_position can close them
                            if item.get("ce", {}).get("label") == "OTM4":
                                tracked_legs.append({
                                    "symbol": item["ce"]["symbol"],
                                    "action": "BUY",
                                    "quantity": self.quantity,
                                    "offset": "OTM4",
                                    "option_type": "CE",
                                    "product": self.product
                                })
                                # For PnL calculation we just put a dummy value if needed,
                                # OptionPositionTracker in SELL mode mainly relies on short legs for PnL if total premium is used,
                                # but wait, we need to pass all legs to tracker so it closes them all.
                                # Memory note: "ensure you filter the execution legs to only include short ('SELL') legs before calling tracker.add_legs()".
                                # If we only add short legs to tracker, _close_position will only close short legs!
                                # Let's create a custom tracker or handle the closing manually.

                                # "When tracking Stop-Loss and Take-Profit for short premium strategies using OpenAlgo's OptionPositionTracker, ensure you filter the execution legs to only include short ('SELL') legs before calling tracker.add_legs(). Failure to do so may cause false premature exits triggered by protective buy legs."

                                # If we do that, we must remember the buy legs separately so we can close the whole IC.

                        # Store all legs for closing later
                        self.all_ic_legs = []
                        for item in chain:
                            for offset, option_type, action in [("OTM2", "CE", "SELL"), ("OTM2", "PE", "SELL"), ("OTM4", "CE", "BUY"), ("OTM4", "PE", "BUY")]:
                                if item.get(option_type.lower(), {}).get("label") == offset:
                                    self.all_ic_legs.append({
                                        "symbol": item[option_type.lower()]["symbol"],
                                        "action": action,
                                        "quantity": self.quantity,
                                        "offset": offset,
                                        "option_type": option_type,
                                        "product": self.product
                                    })

                        # Track only short legs for SL/TP as per memory guidelines
                        short_legs = []
                        short_entry_prices = []
                        for item in chain:
                            if item.get("ce", {}).get("label") == "OTM2":
                                short_legs.append({
                                    "symbol": item["ce"]["symbol"],
                                    "action": "SELL",
                                    "quantity": self.quantity,
                                    "offset": "OTM2",
                                    "option_type": "CE",
                                    "product": self.product
                                })
                                short_entry_prices.append(safe_float(item.get("ce", {}).get("ltp")))
                            elif item.get("pe", {}).get("label") == "OTM2":
                                short_legs.append({
                                    "symbol": item["pe"]["symbol"],
                                    "action": "SELL",
                                    "quantity": self.quantity,
                                    "offset": "OTM2",
                                    "option_type": "PE",
                                    "product": self.product
                                })
                                short_entry_prices.append(safe_float(item.get("pe", {}).get("ltp")))

                        # To make tracker.open_legs act as the closing source, we'll override it or close all_ic_legs.
                        self.tracker.add_legs(short_legs, short_entry_prices, side="SELL")

                        # Override the tracker's open_legs with all legs so _close_position closes the whole condor,
                        # But wait, OptionPositionTracker calculates PnL using tracker.open_legs.
                        # So we must NOT override tracker.open_legs.
                        # We will modify _close_position to use self.all_ic_legs instead.

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondor().run()
