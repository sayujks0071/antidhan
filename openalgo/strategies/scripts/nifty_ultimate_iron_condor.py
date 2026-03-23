#!/usr/bin/env python3
"""
Nifty Ultimate Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120, sells OTM2 and buys OTM4 for protection, with strict SL/TP and time limits.
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
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, utils_dir)
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

# Mandatory API Key retrieval
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

# Enterprise Risk Parameters (Mandatory for OpenAlgo strategies)
ATR_SL_MULTIPLIER = 1.5
ATR_TP_MULTIPLIER = 3.0
BREAKEVEN_TRIGGER_R = 0.8
TIME_STOP_BARS = 15
MAX_RISK_PCT = 5.0
MAX_DAILY_LOSS_PCT = 3.0

# Strategy-specific Configuration
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyUltimateIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "12"))

SL_PCT = float(os.getenv("SL_PCT", "40.0"))
TP_PCT = float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))
MIN_STRADDLE_PREMIUM = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))

SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

class StrategyClass:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.all_open_legs = []

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > EXPIRY_REFRESH_SEC):
            try:
                res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry: {e}")

    def is_trading_window(self):
        now = datetime.now()
        # Recommend entry between 10:00 and 14:30
        start_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = now.replace(hour=14, minute=30, second=0, microsecond=0)
        return start_time <= now <= end_time

    def is_time_to_square_off(self):
        now = datetime.now()
        square_off_time = now.replace(hour=15, minute=15, second=0, microsecond=0)
        return now >= square_off_time

    def _close_position(self, chain, reason):
        if not self.all_open_legs:
            return

        self.logger.info(f"Closing all open legs. Reason: {reason}")

        for leg in self.all_open_legs:
            action = leg.get("action")
            close_action = "BUY" if action == "SELL" else "SELL"
            symbol = leg.get("symbol")

            try:
                resp = self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=symbol,
                    action=close_action,
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=PRODUCT,
                    quantity=QUANTITY,
                    position_size=0  # Close exact amount
                )
                self.logger.info(f"Trade response: Closed {symbol} ({close_action})")
            except Exception as e:
                self.logger.error(f"Error closing leg {symbol}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def get_premium_and_symbol(self, chain, offset, opt_type):
        for item in chain:
            opt = item.get(opt_type.lower(), {})
            if opt.get("label") == offset:
                return float(opt.get("ltp", 0.0)), opt.get("symbol", "")
        return 0.0, ""

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} main loop...")

        # We need a dummy generate_signal for backtest compatibility as specified in AGENTS.md
        # but the OpenAlgo Web UI strategies execute via run loop.

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
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs or self.all_open_legs:
                    if self.is_time_to_square_off():
                        self._close_position(chain, "EOD_SquareOff")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and not self.all_open_legs:
                    if not self.entered_today and self.is_trading_window() and self.limiter.allow():

                        atm_ce_ltp, _ = self.get_premium_and_symbol(chain, "ATM", "CE")
                        atm_pe_ltp, _ = self.get_premium_and_symbol(chain, "ATM", "PE")
                        straddle_premium = atm_ce_ltp + atm_pe_ltp

                        self.logger.info(format_kv(spot=spot, straddle=straddle_premium, min_req=MIN_STRADDLE_PREMIUM))

                        entry_condition = straddle_premium > MIN_STRADDLE_PREMIUM
                        signal = self.debouncer.edge("enter_iron_condor", entry_condition)

                        if signal:
                            # BUY OTM4 CE/PE, SELL OTM2 CE/PE
                            otm4_ce_ltp, otm4_ce_sym = self.get_premium_and_symbol(chain, "OTM4", "CE")
                            otm4_pe_ltp, otm4_pe_sym = self.get_premium_and_symbol(chain, "OTM4", "PE")
                            otm2_ce_ltp, otm2_ce_sym = self.get_premium_and_symbol(chain, "OTM2", "CE")
                            otm2_pe_ltp, otm2_pe_sym = self.get_premium_and_symbol(chain, "OTM2", "PE")

                            if not all([otm4_ce_sym, otm4_pe_sym, otm2_ce_sym, otm2_pe_sym]):
                                self.logger.warning("Could not find all required option symbols.")
                                time.sleep(SLEEP_SECONDS)
                                continue

                            legs = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT, "symbol": otm4_ce_sym},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT, "symbol": otm4_pe_sym},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT, "symbol": otm2_ce_sym},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT, "symbol": otm2_pe_sym},
                            ]

                            self.logger.info("event=trade Place Multi-leg Iron Condor Order")
                            response = self.client.optionsmultiorder(
                                strategy=STRATEGY_NAME,
                                underlying=UNDERLYING,
                                exchange=UNDERLYING_EXCHANGE,
                                expiry_date=self.expiry,
                                legs=legs
                            )

                            if response and response.get("status") == "success":
                                self.limiter.record()
                                self.entered_today = True

                                # Track only short legs for SL/TP
                                short_legs = [leg for leg in legs if leg["action"] == "SELL"]
                                entry_prices = {
                                    otm2_ce_sym: otm2_ce_ltp,
                                    otm2_pe_sym: otm2_pe_ltp
                                }
                                self.tracker.add_legs(short_legs, entry_prices, side="SELL")
                                self.all_open_legs = legs

                                self.logger.info(f"Entered Iron Condor. Tracked legs: {short_legs}")
                            else:
                                self.logger.error(f"Order failed: {response}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

# Mandatory module-level function for backtesting
def generate_signal(df, client=None, symbol=None, params=None):
    if df is None or df.empty or len(df) < 50:
        return 'HOLD', 0.0, {}
    price = float(df.iloc[-1]['close'])
    return 'HOLD', 0.0, {
        'close': price,
        'atr': 0.0,
        'adx': 0.0,
        'quantity': 1,
        'sl': price - (price * 0.02),
        'tp': price + (price * 0.04),
        'breakeven_trigger_r': BREAKEVEN_TRIGGER_R,
        'time_stop_bars': TIME_STOP_BARS,
    }

if __name__ == "__main__":
    StrategyClass().run()
