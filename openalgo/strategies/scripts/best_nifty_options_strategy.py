#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if ATM straddle premium > 120 (sells OTM2, buys OTM4).
"""
import os
import sys
import time
from datetime import datetime, timezone, timedelta

# Line-buffered output (required for real-time log capture)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, utils_dir)
sys.path.insert(0, strategies_dir)
sys.path.insert(0, root_dir)

try:
    from trading_utils import is_market_open, APIClient
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

class StrategyClass:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "best_nifty_options_strategy")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))

        # Risk Management Params
        self.sl_pct = float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "300"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # State and Utilities
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=self.max_orders_per_day, max_per_hour=self.max_orders_per_hour, cooldown_seconds=self.cooldown_seconds)
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False

        self.ist = timezone(timedelta(hours=5, minutes=30))

        self.logger.info(format_kv(msg="Strategy Initialized", strategy=self.strategy_name, underlying=self.underlying))

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res.get("status") == "success" and res.get("data"):
                    self.expiry = choose_nearest_expiry(res["data"])
                    self.last_expiry_refresh = now
                    self.logger.debug(f"Resolved nearest expiry: {self.expiry}")
                else:
                    self.logger.warning(f"Could not fetch expiry dates: {res}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def get_atm_straddle_premium(self, chain):
        atm_ce_ltp = 0.0
        atm_pe_ltp = 0.0
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" or pe.get("label") == "ATM":
                atm_ce_ltp = safe_float(ce.get("ltp"), 0.0)
                atm_pe_ltp = safe_float(pe.get("ltp"), 0.0)
                break
        return atm_ce_ltp + atm_pe_ltp

    def _close_position(self, chain, reason):
        if not self.tracker.open_legs:
            return

        self.logger.info(f"Closing position. Reason: {reason}")

        # Sort legs to close Shorts first (Buy to cover) before Longs (Sell to close) for margin
        # We opened with SELL (OTM2) and BUY (OTM4). To close, we BUY the OTM2 and SELL the OTM4.
        closing_legs = []
        for leg in self.tracker.open_legs:
            closing_action = "BUY" if leg["side"] == "SELL" else "SELL"
            closing_legs.append({
                "symbol": leg["symbol"],
                "action": closing_action,
                "quantity": self.quantity,
                "product": self.product
            })

        # Priority: BUY actions first
        closing_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        # We need to execute smart orders for each leg to close them, as multiorder uses offsets which might shift
        for leg in closing_legs:
            try:
                self.logger.info(format_kv(event="trade", action=leg["action"], symbol=leg["symbol"], reason=reason))
                self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=leg["action"],
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=leg["product"],
                    quantity=leg["quantity"],
                    position_size=0 # Close position
                )
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()

    def run(self):
        self.logger.info("Starting strategy main loop...")
        while True:
            try:
                # Reset daily limits at start of day
                current_time = datetime.now(self.ist)
                if current_time.hour == 9 and current_time.minute < 10:
                    self.entered_today = False

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
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = safe_float(chain_resp.get("underlying_ltp"), 0.0)

                # EXIT MANAGEMENT FIRST (always check exits before entries)
                if self.tracker.open_legs:
                    # EOD Square-off before 3:15 PM
                    if current_time.hour == 15 and current_time.minute >= 15:
                        self._close_position(chain, "eod_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, _, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS
                straddle_premium = self.get_atm_straddle_premium(chain)

                self.logger.debug(format_kv(spot=spot, straddle_premium=straddle_premium, time=current_time.strftime("%H:%M")))

                # ENTRY LOGIC
                # Enters after 10 AM, one trade per day, min premium > 120
                if current_time.hour < 10:
                    time.sleep(self.sleep_seconds)
                    continue

                if self.entered_today:
                    time.sleep(self.sleep_seconds)
                    continue

                if not self.tracker.open_legs and self.limiter.allow():
                    signal_condition = straddle_premium > self.min_straddle_premium

                    if self.debouncer.edge("enter_iron_condor", signal_condition):
                        self.logger.info(format_kv(event="signal", type="iron_condor", straddle=straddle_premium))

                        # Prepare legs for Iron Condor: Sell OTM2, Buy OTM4
                        # BUY legs execute first, then SELL legs (for margin efficiency)
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

                            self.logger.info(f"Trade response: {response}")
                            self.limiter.record()
                            self.entered_today = True

                            # Track position. We need to extract the actual symbols and entry prices from the chain
                            # corresponding to the offsets we traded.

                            entry_legs_info = []
                            entry_prices = []

                            for item in chain:
                                ce = item.get("ce", {})
                                pe = item.get("pe", {})

                                # Process CE legs
                                for leg in legs:
                                    if leg["option_type"] == "CE" and ce.get("label") == leg["offset"]:
                                        entry_legs_info.append({
                                            "symbol": ce.get("symbol"),
                                            "side": leg["action"],
                                            "qty": leg["quantity"]
                                        })
                                        entry_prices.append(safe_float(ce.get("ltp")))

                                # Process PE legs
                                for leg in legs:
                                    if leg["option_type"] == "PE" and pe.get("label") == leg["offset"]:
                                        entry_legs_info.append({
                                            "symbol": pe.get("symbol"),
                                            "side": leg["action"],
                                            "qty": leg["quantity"]
                                        })
                                        entry_prices.append(safe_float(pe.get("ltp")))

                            if len(entry_legs_info) == 4:
                                # tracker.add_legs needs an array of dictionaries with at least 'symbol' and 'side' keys
                                # but the method signature in OptionPositionTracker typically assumes we pass the same array of dictionaries
                                # that it uses to store it, but wait: the signature is tracker.add_legs(legs, entry_prices, side)
                                # Actually `add_legs` expects `legs` as list of dicts that have `symbol` and `side`, but it might overwrite `side`.
                                # Wait, the instructions say: tracker.add_legs(legs, entry_prices, side="SELL")  # or "BUY"
                                # Let's look at OptionPositionTracker to be safe. It accepts `legs` and `entry_prices`.
                                # But wait! We have mixed sides (Iron Condor). Let's just pass them one by one if it needs side="SELL" etc., or pass them all at once if the legs dict has `side` and it doesn't overwrite it.
                                # Let's assume OptionPositionTracker processes each leg's "side" if present, else uses the default `side` arg.
                                # To be safe we will iterate.
                                for i in range(len(entry_legs_info)):
                                    self.tracker.add_legs([entry_legs_info[i]], [entry_prices[i]], side=entry_legs_info[i]["side"])
                                self.logger.info(f"Position tracker started with {len(self.tracker.open_legs)} legs")
                            else:
                                self.logger.warning("Could not map all offsets to symbols from chain.")

                        except Exception as trade_err:
                            self.logger.error(f"Error placing multi-leg order: {trade_err}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
