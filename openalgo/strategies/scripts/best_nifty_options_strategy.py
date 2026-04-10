#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy that enters after 10 AM if straddle premium > 120, taking 1 trade per day.
"""
import os
import sys
import time
from datetime import datetime, time as dt_time

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
        normalize_expiry,
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


# --- Configuration & Auth Setup ---
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

# Parameters from memory & prompt for Nifty Iron Condor
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "best_nifty_options_strategy")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"), 1)
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

# Specific rules
SL_PCT = safe_float(os.getenv("SL_PCT", "40"), 40.0)
TP_PCT = safe_float(os.getenv("TP_PCT", "50"), 50.0)
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "120"), 120)
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "30"), 30)
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)

MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)


class NiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.trade_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.debouncer = SignalDebouncer()

        self.expiry = os.getenv("EXPIRY_DATE", "")
        self.last_expiry_refresh = time.time() if self.expiry else 0
        from datetime import timezone, timedelta
        self.ist = timezone(timedelta(hours=5, minutes=30))
        self.entered_today = False
        self.last_trade_date = None

    def can_trade(self):
        """Time and logic constraints for entry"""
        now = datetime.now(self.ist)
        current_time = now.time()
        current_date = now.date()

        if self.last_trade_date != current_date:
            self.entered_today = False
            self.last_trade_date = current_date

        if self.entered_today:
            return False

        # Enter after 10:00 AM, up to 2:30 PM
        start_time = dt_time(10, 0)
        end_time = dt_time(14, 30)

        if not (start_time <= current_time <= end_time):
            return False

        return self.limiter.allow()

    def check_eod_square_off(self):
        """Force exit before 3:15 PM"""
        now = datetime.now(self.ist)
        if now.time() >= dt_time(15, 15):
            return True
        return False

    def ensure_expiry(self):
        """Auto-resolve nearest expiry"""
        now_ts = time.time()
        if self.expiry and (now_ts - self.last_expiry_refresh) < EXPIRY_REFRESH_SEC:
            return

        try:
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res and isinstance(res, dict) and res.get("status") == "success":
                dates = res.get("data", [])
                if dates:
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_refresh = now_ts
                    self.logger.info(f"Selected Expiry: {self.expiry}")
        except Exception as e:
            self.logger.error(f"Error fetching expiry: {e}")

    def _close_position(self, chain, reason):
        """Close current position by calculating current exit prices from the chain."""
        self.logger.info(format_kv(event="trade", action="EXIT", reason=reason))

        # Sort legs to prioritize BUY to cover (closing short legs) before SELL
        sorted_legs = []
        for leg in self.tracker.open_legs:
            leg_sym = leg.get("symbol")
            open_side = leg.get("side")
            close_action = "BUY" if open_side == "SELL" else "SELL"
            qty = leg.get("quantity", QUANTITY)
            sorted_legs.append({"symbol": leg_sym, "close_action": close_action, "quantity": qty})

        sorted_legs.sort(key=lambda x: 0 if x["close_action"] == "BUY" else 1)

        for leg_info in sorted_legs:
            leg_sym = leg_info["symbol"]
            close_action = leg_info["close_action"]
            qty = leg_info["quantity"]

            self.logger.info(format_kv(event="trade", symbol=leg_sym, action=close_action, reason=reason))

            try:
                resp = self.trade_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=leg_sym,
                    action=close_action,
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=PRODUCT,
                    quantity=qty,
                    position_size=qty
                )
                if resp and resp.get("status") == "success":
                    self.logger.info(f"Exit order placed successfully for {leg_sym}")
                else:
                    self.logger.error(f"Failed to place exit order for {leg_sym}: {resp}")
            except Exception as e:
                self.logger.error(f"Exception while placing exit order for {leg_sym}: {e}")

            # Sleep slightly between leg orders
            time.sleep(1)

        self.tracker.clear()

    def run(self):
        self.logger.info("Starting Nifty Iron Condor Strategy...")
        while True:
            try:
                # 1. Market Open Check
                if not is_market_open():
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 2. Expiry Ensure
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch Options Chain
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )
                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False)
                if not valid:
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)

                # 4. EOD Square Off Check
                if self.tracker.open_legs and self.check_eod_square_off():
                    self._close_position(chain, "eod_square_off")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 5. Exit Management
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # 6. Entry Logic
                if not self.tracker.open_legs and self.can_trade():
                    # Calculate Straddle Premium
                    atm_item = None
                    for item in chain:
                        if item.get("ce", {}).get("label") == "ATM":
                            atm_item = item
                            break

                    if atm_item:
                        ce_ltp = safe_float(atm_item.get("ce", {}).get("ltp", 0.0))
                        pe_ltp = safe_float(atm_item.get("pe", {}).get("ltp", 0.0))
                        straddle_premium = ce_ltp + pe_ltp

                        self.logger.debug(format_kv(spot=spot, straddle_prem=straddle_premium))

                        # Condition: Straddle premium > 120
                        signal_condition = straddle_premium > 120
                        signal = self.debouncer.edge("entry_signal", signal_condition)

                        if signal:
                            # We want to sell OTM2 CE/PE and buy OTM4 CE/PE.
                            # BUT rule says: BUY legs execute first, then SELL legs (for margin efficiency)

                            # Construct legs & grab entry prices
                            legs_config = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                            ]

                            # Execute Order
                            self.logger.info(format_kv(event="trade", action="ENTRY", strategy=STRATEGY_NAME))
                            response = self.client.optionsmultiorder(
                                strategy=STRATEGY_NAME,
                                underlying=UNDERLYING,
                                exchange=UNDERLYING_EXCHANGE,
                                expiry_date=self.expiry,
                                legs=legs_config
                            )

                            if response and response.get("status") == "success":
                                self.limiter.record()
                                self.entered_today = True

                                # Find exact entry prices from the chain
                                entry_prices = []
                                tracker_legs = []

                                # Build tracker legs mapping explicitly by finding matching labels in chain
                                for cfg in legs_config:
                                    offset = cfg["offset"]
                                    opt_type = cfg["option_type"].lower()
                                    matched_item = None

                                    for item in chain:
                                        if item.get(opt_type, {}).get("label") == offset:
                                            matched_item = item.get(opt_type, {})
                                            break

                                    if matched_item:
                                        sym = matched_item.get("symbol")
                                        ltp = safe_float(matched_item.get("ltp", 0.0))
                                        entry_prices.append(ltp)
                                        tracker_legs.append({
                                            "symbol": sym,
                                            "side": cfg["action"],
                                            "quantity": QUANTITY
                                        })
                                    else:
                                        # Fallback in case of missing label
                                        entry_prices.append(0.0)
                                        tracker_legs.append({
                                            "symbol": "UNKNOWN",
                                            "side": cfg["action"],
                                            "quantity": QUANTITY
                                        })

                                # Tracker needs: tracker.add_legs(legs, entry_prices)
                                # where `legs` is the list of dicts.
                                self.tracker.add_legs(tracker_legs, entry_prices)
                                self.logger.info(f"Trade response: Entry successful. Tracker initialized with prices: {entry_prices}")
                            else:
                                self.logger.error(f"Trade response: Multi-order failed: {response}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    NiftyIronCondor().run()
