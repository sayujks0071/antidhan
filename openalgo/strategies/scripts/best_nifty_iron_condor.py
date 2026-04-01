#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM if straddle premium > 120, sells OTM2, buys OTM4 for protection. 40% SL, 50% TP, 45m hold, 1 trade/day.
"""
import os
import sys
import time
from datetime import datetime, time as datetime_time

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


# Configuration Section
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "BestNiftyIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY"), 1)
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT"), 12)

SL_PCT = safe_float(os.getenv("SL_PCT"), 40.0)
TP_PCT = safe_float(os.getenv("TP_PCT"), 50.0)
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN"), 45)

COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS"), 120)
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS"), 30)
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC"), 300)

MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY"), 1)
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR"), 1)

MIN_STRADDLE_PREMIUM = safe_float(os.getenv("MIN_STRADDLE_PREMIUM"), 120.0)

# API Key retrieval
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
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.limiter = TradeLimiter(max_per_day=MAX_ORDERS_PER_DAY, max_per_hour=MAX_ORDERS_PER_HOUR, cooldown_seconds=COOLDOWN_SECONDS)
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.last_trade_date = None
        self.all_open_legs = []

        self.logger.info(f"Initialized {STRATEGY_NAME} with SL: {SL_PCT}%, TP: {TP_PCT}%, Max Hold: {MAX_HOLD_MIN}m")

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > EXPIRY_REFRESH_SEC):
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res and isinstance(res, dict) and res.get("status") == "success":
                exp_list = res.get("data", [])
                if exp_list:
                    self.expiry = choose_nearest_expiry(exp_list)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Using expiry: {self.expiry}")

    def _get_atm_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            if ce.get("label") == "ATM":
                pe = item.get("pe", {})
                return safe_float(ce.get("ltp")) + safe_float(pe.get("ltp"))
        return 0.0

    def _close_position(self, chain, exit_reason):
        if not self.tracker.open_legs:
            return

        self.logger.info(f"Closing position. Reason: {exit_reason}")

        # We need to reverse the position to close
        close_legs = getattr(self, "all_open_legs", self.tracker.open_legs)
        if not close_legs:
            close_legs = self.tracker.open_legs

        try:
            from trading_utils import APIClient
            api_client = APIClient(api_key=API_KEY, host=HOST)

            close_actions = []
            for leg in close_legs:
                orig_action = leg.get("action")
                symbol = leg.get("symbol")
                qty = leg.get("quantity", QUANTITY)
                close_action = "BUY" if orig_action == "SELL" else "SELL"
                close_actions.append({
                    "symbol": symbol,
                    "action": close_action,
                    "quantity": qty
                })

            # Sort: BUY first, SELL second
            close_actions.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

            for action_dict in close_actions:
                resp = api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=action_dict["symbol"],
                    action=action_dict["action"],
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=PRODUCT,
                    quantity=action_dict["quantity"],
                    position_size=0
                )
                self.logger.info(f"Trade response: Closed {action_dict['symbol']} via {action_dict['action']}. Resp: {resp}")
        except Exception as e:
            self.logger.error(f"Error closing positions individually: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def can_trade_now(self):
        now = datetime.now()
        current_date = now.date()

        if self.last_trade_date != current_date:
            self.last_trade_date = current_date
            self.entered_today = False

        if self.entered_today:
            return False

        t = now.time()
        # Enters after 10 AM, exits all by 15:15
        if t < datetime_time(10, 0) or t >= datetime_time(15, 10):
            return False

        return self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting main loop for {STRATEGY_NAME}")
        while True:
            try:
                if not is_market_open():
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp"))

                # EOD Square-off
                now_t = datetime.now().time()
                if now_t >= datetime_time(15, 15) and self.tracker.open_legs:
                    self._close_position(chain, "eod_square_off")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs:
                    straddle_premium = self._get_atm_straddle_premium(chain)

                    if straddle_premium > 0:
                        self.logger.info(format_kv(spot=underlying_ltp, premium=straddle_premium, min_required=MIN_STRADDLE_PREMIUM))

                    entry_condition = (straddle_premium > MIN_STRADDLE_PREMIUM) and self.can_trade_now()

                    if self.debouncer.edge("iron_condor_entry", entry_condition):
                        self.logger.info(f"Entry condition met. Premium: {straddle_premium} > {MIN_STRADDLE_PREMIUM}")

                        legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                        ]

                        resp = self.client.optionsmultiorder(
                            strategy=STRATEGY_NAME,
                            underlying=UNDERLYING,
                            exchange=UNDERLYING_EXCHANGE,
                            expiry_date=self.expiry,
                            legs=legs
                        )

                        self.logger.info(f"event=trade action=optionsmultiorder response={resp}")

                        # We need to extract the actual executed symbols from the chain to add to tracker
                        # The tracker expects legs with 'symbol', 'entry_price', 'action'
                        # We find the symbols from the chain based on offsets
                        executed_legs = []
                        entry_prices = []

                        for req_leg in legs:
                            offset = req_leg["offset"]
                            opt_type = req_leg["option_type"].lower()

                            # Find matching option in chain
                            for item in chain:
                                opt = item.get(opt_type, {})
                                if opt.get("label") == offset:
                                    executed_legs.append({
                                        "symbol": opt.get("symbol"),
                                        "action": req_leg["action"],
                                        "quantity": req_leg["quantity"]
                                    })
                                    entry_prices.append(safe_float(opt.get("ltp")))
                                    break

                        if len(executed_legs) == 4:
                            short_legs = []
                            short_prices = []
                            for i, leg in enumerate(executed_legs):
                                if leg["action"] == "SELL":
                                    short_legs.append(leg)
                                    short_prices.append(entry_prices[i])

                            self.all_open_legs = executed_legs
                            self.tracker.add_legs(short_legs, short_prices, side="SELL")

                            self.entered_today = True
                            self.limiter.record()
                        else:
                            self.logger.warning(f"Could not find all leg symbols in chain to track. Executed: {executed_legs}")

                time.sleep(SLEEP_SECONDS)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    StrategyClass().run()
