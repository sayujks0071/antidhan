#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120. Sells OTM2 CE/PE, Buys OTM4 CE/PE.
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


# Strategy Configuration
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NIFTY_IRON_CONDOR")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "12"))

SL_PCT = float(os.getenv("SL_PCT", "40"))
TP_PCT = float(os.getenv("TP_PCT", "50"))
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))

COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

MIN_STRADDLE_PREMIUM = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))


class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.debouncer = SignalDebouncer()

        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )

        self.expiry = None
        self.last_expiry_check = 0
        self.current_date = datetime.now().date()
        self.entered_today = False

        self.all_open_legs = []

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check) > EXPIRY_REFRESH_SEC:
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                self.expiry = choose_nearest_expiry(dates)
                self.last_expiry_check = now
                self.logger.info(f"Resolved Expiry: {self.expiry}")

    def _close_position(self, reason):
        if not self.all_open_legs:
            return

        self.logger.info(f"Closing position. Reason: {reason}")

        # Close each leg individually
        for leg in self.all_open_legs:
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            try:
                res = self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=PRODUCT,
                    quantity=leg["quantity"],
                    position_size=0
                )
                self.logger.info(f"event=trade Trade response: {res}")
            except Exception as e:
                self.logger.error(f"Failed to close leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def can_trade(self, now_time):
        # Entry window: 10:00 AM to 2:30 PM (14:30)
        start_time = datetime.strptime("10:00", "%H:%M").time()
        end_time = datetime.strptime("14:30", "%H:%M").time()
        return start_time <= now_time <= end_time

    def _execute_entry(self, chain):
        self.logger.info("Executing Iron Condor Entry...")

        # BUY legs execute first, then SELL legs (for margin efficiency)
        legs_config = [
            {"offset": "OTM4", "option_type": "CE", "action": "BUY"},
            {"offset": "OTM4", "option_type": "PE", "action": "BUY"},
            {"offset": "OTM2", "option_type": "CE", "action": "SELL"},
            {"offset": "OTM2", "option_type": "PE", "action": "SELL"}
        ]

        resolved_legs = []
        api_legs = []

        for cfg in legs_config:
            offset = cfg["offset"]
            otype = cfg["option_type"].lower()

            found_item = None
            for item in chain:
                opt = item.get(otype, {})
                if opt.get("label") == offset:
                    found_item = opt
                    break

            if found_item:
                symbol = found_item.get("symbol")
                ltp = safe_float(found_item.get("ltp"))

                if symbol:
                    api_legs.append({
                        "offset": offset,
                        "option_type": cfg["option_type"],
                        "action": cfg["action"],
                        "quantity": QUANTITY,
                        "product": PRODUCT
                    })

                    resolved_legs.append({
                        "symbol": symbol,
                        "option_type": cfg["option_type"],
                        "action": cfg["action"],
                        "quantity": QUANTITY,
                        "entry_price": ltp,
                        "product": PRODUCT
                    })
            else:
                self.logger.warning(f"Could not resolve {offset} {cfg['option_type']}")
                return

        if len(resolved_legs) != len(legs_config):
            self.logger.error("Failed to resolve all required legs.")
            return

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=api_legs
            )

            if res.get("status") == "success":
                self.logger.info(f"event=trade Trade response: {res}")

                # Maintain all open legs
                self.all_open_legs = resolved_legs

                # Only add short ('SELL') legs to tracker for short premium strategies
                short_legs = [leg for leg in resolved_legs if leg["action"] == "SELL"]
                short_entry_prices = [leg["entry_price"] for leg in short_legs]

                if short_legs:
                    self.tracker.add_legs(short_legs, short_entry_prices, side="SELL")

                self.entered_today = True
                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # 0. Daily Reset
                now_dt = datetime.now()
                if now_dt.date() != self.current_date:
                    self.entered_today = False
                    self.current_date = now_dt.date()
                    # Limiter checks daily limits internally, but let's re-init to be safe
                    self.limiter = TradeLimiter(
                        max_per_day=MAX_ORDERS_PER_DAY,
                        max_per_hour=MAX_ORDERS_PER_HOUR,
                        cooldown_seconds=COOLDOWN_SECONDS
                    )

                # 1. Market Hours Check
                market_open = True
                try:
                    if not is_market_open():
                        market_open = False
                except:
                    pass

                if not market_open:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 2. Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch Data
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT,
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=STRIKE_COUNT)
                if not valid:
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # 4. Exit Management FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Exit 3:15 PM
                    now_time = datetime.now().time()
                    eod_time = datetime.strptime("15:15", "%H:%M").time()

                    if now_time >= eod_time:
                        exit_now = True
                        exit_reason = "eod_sqoff"

                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # 5. Entry Logic
                if not self.tracker.open_legs and not self.entered_today:
                    now_time = datetime.now().time()
                    can_trade_now = self.can_trade(now_time)

                    atm_strike = chain_resp.get("atm_strike")
                    if not atm_strike:
                        atm_strike = underlying_ltp

                    atm_item = None
                    for item in chain:
                        if safe_float(item.get("strike")) == safe_float(atm_strike):
                            atm_item = item
                            break
                    if not atm_item:
                        for item in chain:
                            if item.get("ce", {}).get("label") == "ATM":
                                atm_item = item
                                break

                    straddle_premium = 0.0
                    if atm_item:
                        ce_ltp = safe_float(atm_item.get("ce", {}).get("ltp"))
                        pe_ltp = safe_float(atm_item.get("pe", {}).get("ltp"))
                        straddle_premium = ce_ltp + pe_ltp

                    self.logger.info(format_kv(
                        spot=f"{underlying_ltp:.2f}",
                        straddle=f"{straddle_premium:.2f}",
                        pos="FLAT" if not self.all_open_legs else "OPEN"
                    ))

                    should_enter = (straddle_premium > MIN_STRADDLE_PREMIUM)

                    if self.debouncer.edge("entry_signal", should_enter and can_trade_now):
                        if self.limiter.allow():
                            self._execute_entry(chain)

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftyIronCondorStrategy()
    strategy.run()
