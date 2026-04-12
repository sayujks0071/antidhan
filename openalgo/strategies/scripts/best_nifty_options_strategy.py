#!/usr/bin/env python3
"""
BestNiftyOptionsStrategy - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor: Sells OTM2 CE/PE, buys OTM4 CE/PE, enters >10 AM with >120 straddle premium.
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
except ImportError as e:
    print(f"ERROR: Could not import strategy utilities: {e}", flush=True)
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


class BestNiftyOptionsStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "best_nifty_options")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk and Rules
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # Strategy Specific params
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))
        self.sell_offset = os.getenv("SELL_OFFSET", "OTM2")
        self.buy_offset = os.getenv("BUY_OFFSET", "OTM4")

        # Internal State
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds,
        )
        self.debouncer = SignalDebouncer()

        self.expiry_date = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0

    def ensure_expiry(self):
        if self.expiry_date and time.time() - self.last_expiry_refresh < self.expiry_refresh_sec:
            return

        resp = self.client.expiry(self.underlying, self.options_exchange, "options")
        if resp.get("status") == "success" and resp.get("data"):
            expirations = resp["data"]
            self.expiry_date = choose_nearest_expiry(expirations)
            self.last_expiry_refresh = time.time()
            self.logger.info(f"Resolved nearest expiry: {self.expiry_date}")
        else:
            self.logger.warning(f"Failed to get expiry dates: {resp}")

    def get_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM":
                ce_ltp = safe_float(ce.get("ltp"), 0.0)
                pe_ltp = safe_float(pe.get("ltp"), 0.0)
                return ce_ltp + pe_ltp
        return 0.0

    def _close_position(self, chain, exit_reason):
        self.logger.info(f"Closing position. Reason: {exit_reason}")
        open_legs = self.tracker.open_legs

        # Priority: Close short legs first (BUY to cover), then long legs (SELL to close)
        buy_to_cover = [leg for leg in open_legs if leg.get("action") == "SELL"]
        sell_to_close = [leg for leg in open_legs if leg.get("action") == "BUY"]

        def _execute_close(legs, close_action):
            for leg in legs:
                symbol = leg.get("symbol")
                qty = leg.get("quantity")
                try:
                    resp = self.api_client.placesmartorder(
                        strategy=self.strategy_name,
                        symbol=symbol,
                        action=close_action,
                        exchange=self.options_exchange,
                        pricetype="MARKET",
                        product=self.product,
                        quantity=qty,
                        position_size=0
                    )
                    self.logger.info(f"event=trade action={close_action} symbol={symbol} qty={qty} status={resp.get('status')}")
                except Exception as e:
                    self.logger.error(f"Failed to close leg {symbol}: {e}")

        _execute_close(buy_to_cover, "BUY")
        _execute_close(sell_to_close, "SELL")
        self.tracker.clear()

    def can_trade(self):
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)

        # Time filter: > 10 AM, < 3:00 PM
        if now.hour < 10 or (now.hour == 10 and now.minute < 0):
            return False
        if now.hour > 14 or (now.hour == 15 and now.minute >= 0):
            return False

        return self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} for {self.underlying}")
        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry_date:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry_date,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    ist = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist)
                    # EOD Square-off 3:15 PM
                    if now.hour == 15 and now.minute >= 15:
                        exit_now = True
                        exit_reason = "eod_squareoff"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    straddle_premium = self.get_straddle_premium(chain)
                    spot = safe_float(chain_resp.get("underlying_ltp"))

                    self.logger.info(format_kv(spot=spot, straddle_premium=straddle_premium, limit_trades_today=self.limiter.trades_today))

                    signal_condition = straddle_premium >= self.min_straddle_premium

                    if self.debouncer.edge("entry_signal", signal_condition):
                        self.logger.info("Entry signal detected. Placing Iron Condor order.")

                        # Find specific symbols and prices for tracker
                        entry_prices = []
                        track_legs = []
                        api_legs = []

                        # Order of legs in API for margin benefit: BUY before SELL
                        config_legs = [
                            {"offset": self.buy_offset, "option_type": "CE", "action": "BUY"},
                            {"offset": self.buy_offset, "option_type": "PE", "action": "BUY"},
                            {"offset": self.sell_offset, "option_type": "CE", "action": "SELL"},
                            {"offset": self.sell_offset, "option_type": "PE", "action": "SELL"}
                        ]

                        leg_ready = True
                        for leg in config_legs:
                            found = False
                            for item in chain:
                                opt_data = item.get(leg["option_type"].lower(), {})
                                if opt_data.get("label") == leg["offset"]:
                                    api_legs.append({
                                        "offset": leg["offset"],
                                        "option_type": leg["option_type"],
                                        "action": leg["action"],
                                        "quantity": self.quantity,
                                        "product": self.product
                                    })
                                    track_legs.append({
                                        "symbol": opt_data.get("symbol"),
                                        "action": leg["action"],
                                        "quantity": self.quantity
                                    })
                                    entry_prices.append(safe_float(opt_data.get("ltp")))
                                    found = True
                                    break
                            if not found:
                                self.logger.warning(f"Could not find offset {leg['offset']} {leg['option_type']} in chain")
                                leg_ready = False
                                break

                        if leg_ready:
                            response = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.underlying_exchange,
                                expiry_date=self.expiry_date,
                                legs=api_legs
                            )
                            if response.get("status") == "success":
                                self.tracker.add_legs(track_legs, entry_prices, side="SELL")
                                self.limiter.record()
                                self.logger.info(f"event=trade action=ENTER strategy={self.strategy_name} status=success")
                            else:
                                self.logger.error(f"Multi-leg order failed: {response}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    BestNiftyOptionsStrategy().run()
