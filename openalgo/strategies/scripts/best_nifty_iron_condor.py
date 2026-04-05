#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy targeting 10 AM entry with defined risk and strict exit rules.
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


class StrategyClass:
    def __init__(self):
        self.logger = PrintLogger()

        # Configuration Section
        self.strategy_name = os.getenv("STRATEGY_NAME", "best_nifty_ic")
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

        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Internal state
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
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
        self.all_open_legs = []  # To track all legs, including protective ones

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            manual_expiry = os.getenv("EXPIRY_DATE")
            if manual_expiry:
                self.expiry = manual_expiry
                self.logger.info(f"Using manual expiry: {self.expiry}")
            else:
                try:
                    res = self.client.expiry(self.underlying, self.options_exchange, "options")
                    if res and res.get("status") == "success" and res.get("data"):
                        expiries = res.get("data")
                        self.expiry = choose_nearest_expiry(expiries)
                        self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                except Exception as e:
                    self.logger.error(f"Failed to fetch expiry dates: {e}")
            self.last_expiry_refresh = now

    def _get_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" and pe.get("label") == "ATM":
                ce_ltp = safe_float(ce.get("ltp"))
                pe_ltp = safe_float(pe.get("ltp"))
                return ce_ltp + pe_ltp
        return 0.0

    def can_trade(self):
        now = datetime.now()
        # Time-based filters: 10:00 to 14:30
        if now.hour < 10:
            return False
        if now.hour == 14 and now.minute > 30:
            return False
        if now.hour > 14:
            return False

        if self.entered_today:
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        self.logger.info(format_kv(event="trade", action="close_position", reason=reason))

        # Need to sort legs: BUY to cover (closing short legs) before SELL to close (closing long legs)
        closing_actions = []
        for leg in self.all_open_legs:
            side = leg.get("action")
            close_action = "BUY" if side == "SELL" else "SELL"
            symbol = leg.get("symbol")

            if not symbol:
                # Fallback if symbol wasn't saved (shouldn't happen with new logic)
                option_type = leg.get("option_type", "").upper()
                offset = leg.get("offset")
                for item in chain:
                    opt = item.get(option_type.lower(), {})
                    if opt.get("label") == offset:
                        symbol = opt.get("symbol")
                        break

            if not symbol:
                self.logger.warning(f"Could not find symbol to close for leg: {leg}")
                continue

            closing_actions.append({
                "symbol": symbol,
                "action": close_action,
                "quantity": self.quantity,
                "pricetype": "MARKET",
                "product": self.product,
                "priority": 1 if close_action == "BUY" else 2
            })

        # Sort so BUY comes first
        closing_actions.sort(key=lambda x: x["priority"])

        for action in closing_actions:
            try:
                self.logger.info(f"Closing leg: {action['action']} {action['symbol']}")
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=action["symbol"],
                    action=action["action"],
                    exchange=self.options_exchange,
                    pricetype=action["pricetype"],
                    product=action["product"],
                    quantity=action["quantity"],
                    position_size=0
                )
                self.logger.info(f"Trade response: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {action['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} strategy loop")
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
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EOD Square-off before 3:15 PM
                now = datetime.now()
                is_eod = (now.hour == 15 and now.minute >= 15) or now.hour > 15

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs or self.all_open_legs:
                    if is_eod:
                        self._close_position(chain, "eod_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS
                straddle_premium = self._get_straddle_premium(chain)
                spot = safe_float(chain_resp.get("underlying_ltp"))

                if now.minute % 5 == 0 and now.second < self.sleep_seconds:
                    self.logger.info(format_kv(spot=spot, premium=straddle_premium, open_legs=len(self.all_open_legs)))

                # ENTRY LOGIC
                if not self.all_open_legs and not is_eod and self.can_trade():
                    # Iron Condor entry condition
                    if straddle_premium > self.min_straddle_premium:
                        signal = self.debouncer.edge("ic_entry", True)
                        if signal:
                            self.logger.info(format_kv(event="trade_signal", signal="ic_entry", premium=straddle_premium))
                            self.limiter.record()
                            self.entered_today = True

                            legs_to_order = [
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
                                    legs=legs_to_order
                                )
                                self.logger.info(f"Trade response: {response}")

                                # Track only the short legs for TP/SL to avoid false exits on protective wings
                                short_legs = []
                                short_prices = []

                                for leg in legs_to_order:
                                    # Find actual symbol and entry price from chain before saving
                                    entry_price = 0.0
                                    symbol = None
                                    opt_type = leg["option_type"].lower()
                                    for item in chain:
                                        opt = item.get(opt_type, {})
                                        if opt.get("label") == leg["offset"]:
                                            entry_price = safe_float(opt.get("ltp"))
                                            symbol = opt.get("symbol")
                                            break

                                    # Save the resolved symbol to the leg
                                    if symbol:
                                        leg["symbol"] = symbol
                                    else:
                                        self.logger.warning(f"Could not resolve symbol for offset {leg['offset']} {leg['option_type']}")

                                    self.all_open_legs.append(leg)

                                    if leg["action"] == "SELL":
                                        short_legs.append(leg)
                                        short_prices.append(entry_price)

                                if short_legs and all(p > 0 for p in short_prices):
                                    self.tracker.add_legs(short_legs, short_prices, side="SELL")
                                    self.logger.info(f"Tracking short legs at prices: {short_prices}")
                                else:
                                    self.logger.warning("Could not find valid entry prices for short legs to track")
                            except Exception as e:
                                self.logger.error(f"Error placing multi-leg order: {e}")

            except Exception as e:
                self.logger.error(f"Error in strategy loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    StrategyClass().run()
