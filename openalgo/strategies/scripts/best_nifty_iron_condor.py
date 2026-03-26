#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor trading strategy entering after 10 AM, requiring straddle > 120, SL 40%, TP 50%, hold 45 mins.
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

# Configuration via Environment Variables
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "BestNiftyIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "12"))

# Risk Management Defaults
SL_PCT = float(os.getenv("SL_PCT", "40"))
TP_PCT = float(os.getenv("TP_PCT", "50"))
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))

# Operational Defaults
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "120"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Strategy Logic Defaults
MIN_STRADDLE_PREMIUM = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))


class StrategyClass:
    def __init__(self):
        self.logger = PrintLogger()
        self.logger.info(f"Starting {STRATEGY_NAME}...")

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.debouncer = SignalDebouncer()

        # State
        self.manual_expiry = os.getenv("EXPIRY_DATE", None)
        self.expiry = self.manual_expiry
        self.last_expiry_check = 0
        self.entered_today = False
        self.all_open_legs = []  # Maintain all executed legs including buys
        self.current_day = datetime.now().date()

    def ensure_expiry(self):
        if self.manual_expiry:
            return  # Skip refresh if user manually specified expiry date

        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > EXPIRY_REFRESH_SEC):
            try:
                res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_check = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def get_straddle_premium(self, chain):
        for item in chain:
            ce_label = item.get("ce", {}).get("label")
            pe_label = item.get("pe", {}).get("label")

            if ce_label == "ATM" or pe_label == "ATM":
                ce_ltp = safe_float(item.get("ce", {}).get("ltp"), 0.0)
                pe_ltp = safe_float(item.get("pe", {}).get("ltp"), 0.0)
                return ce_ltp + pe_ltp
        return 0.0

    def can_trade(self):
        now = datetime.now()

        if now.date() != self.current_day:
            self.current_day = now.date()
            self.entered_today = False

        if self.entered_today:
            return False

        start_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = now.replace(hour=14, minute=30, second=0, microsecond=0)

        if now < start_time or now > end_time:
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position. Reason: {reason}")

        try:
            api = APIClient(api_key=API_KEY, host=HOST)

            for leg in self.all_open_legs:
                symbol = leg.get("symbol")
                close_action = "BUY" if leg.get("action") == "SELL" else "SELL"
                qty = leg.get("quantity", QUANTITY)

                resp = api.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=symbol,
                    action=close_action,
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=PRODUCT,
                    quantity=qty,
                    position_size=0
                )
                self.logger.info(f"Trade response for closing {symbol}: {resp}")
        except Exception as e:
            self.logger.error(f"Error closing position: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def force_eod_exit(self, chain):
        now = datetime.now()
        eod_time = now.replace(hour=15, minute=15, second=0, microsecond=0)
        if now >= eod_time and (self.tracker.open_legs or self.all_open_legs):
            self._close_position(chain, "EOD_Square_off")
            return True
        return False

    def run(self):
        self.logger.info(f"Running {STRATEGY_NAME} Strategy loop...")
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.debug(f"Invalid chain data: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")

                if self.force_eod_exit(chain):
                    time.sleep(SLEEP_SECONDS)
                    continue

                if self.tracker.open_legs:
                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                straddle_premium = self.get_straddle_premium(chain)

                if not self.tracker.open_legs and not self.all_open_legs:
                    condition = straddle_premium > MIN_STRADDLE_PREMIUM

                    if self.debouncer.edge("iron_condor_entry", condition and self.can_trade()):
                        self.logger.info(format_kv(spot=atm_strike, straddle=straddle_premium, signal="ENTRY_IRON_CONDOR"))

                        legs_req = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                        ]

                        response = self.client.optionsmultiorder(
                            strategy=STRATEGY_NAME,
                            underlying=UNDERLYING,
                            exchange=OPTIONS_EXCHANGE,
                            expiry_date=self.expiry,
                            legs=legs_req
                        )

                        if response and response.get("status") == "success":
                            self.logger.info(f"event=trade response={response}")
                            self.limiter.record()
                            self.entered_today = True

                            executed_legs = response.get("data", [])
                            if executed_legs:
                                self.all_open_legs = executed_legs

                                short_legs = [leg for leg in executed_legs if leg.get("action") == "SELL"]

                                entry_prices = []
                                for leg in short_legs:
                                    entry_prices.append(leg.get("ltp") or leg.get("average_price") or leg.get("price") or 0.0)

                                self.tracker.add_legs(short_legs, entry_prices, side="SELL")
                                self.logger.info(format_kv(tracked_short_legs=len(short_legs), total_legs=len(executed_legs)))
                        else:
                            self.logger.error(f"Order placement failed: {response}")

            except Exception as e:
                self.logger.error(f"Error in strategy loop: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    StrategyClass().run()
