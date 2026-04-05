#!/usr/bin/env python3
"""
Ultimate Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM when straddle premium > 120. Sells OTM2, Buys OTM4.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

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
        safe_float,
        safe_int
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


# Configuration Section
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyUltimateIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Strategy Parameters
MIN_STRADDLE_PREMIUM = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))

# Time Windows (IST)
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "10:00")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")

# Risk Parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "40.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

# Rate Limiting
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Manual Expiry Override
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()


class NiftyUltimateIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.expiry = EXPIRY_DATE
        self.last_expiry_check = 0
        self.entered_today = False
        self.current_date = datetime.now().date()

        # To avoid offset drift, explicitly save executed leg details
        self.all_open_legs = []
        self.entry_time = None

    def ensure_expiry(self):
        if self.expiry and (time.time() - self.last_expiry_check < EXPIRY_REFRESH_SEC):
            return

        self.logger.info("Fetching available expiry dates...")
        try:
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.last_expiry_check = time.time()
                    self.logger.info(f"Selected expiry: {self.expiry}")
                else:
                    self.logger.warning("No valid future expiry found.")
            else:
                self.logger.error(f"Failed to fetch expiry: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Expiry fetch error: {e}")

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position. Reason: {reason}")
        if not self.all_open_legs:
            return

        legs_to_close = []
        for leg in self.all_open_legs:
            close_leg = {
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": "BUY" if leg["action"] == "SELL" else "SELL",
                "quantity": leg["quantity"],
                "product": leg.get("product", PRODUCT)
            }
            legs_to_close.append(close_leg)

        # BUY actions (closing shorts) first
        legs_to_close.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=legs_to_close
            )
            self.logger.info(f"Exit Order Response: {res}")

            if res.get("status") == "success":
                self.tracker.clear()
                self.all_open_legs = []
            else:
                self.logger.error(f"Exit failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _open_position(self, chain, straddle_premium):
        self.logger.info(f"Attempting to open Iron Condor (Straddle: {straddle_premium:.2f})...")

        legs_config = [
            {"offset": "OTM4", "option_type": "CE", "action": "BUY"},
            {"offset": "OTM4", "option_type": "PE", "action": "BUY"},
            {"offset": "OTM2", "option_type": "CE", "action": "SELL"},
            {"offset": "OTM2", "option_type": "PE", "action": "SELL"},
        ]

        resolved_legs = []
        api_legs = []
        short_legs_for_tracker = []

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

                api_legs.append({
                    "symbol": symbol,
                    "option_type": cfg["option_type"],
                    "action": cfg["action"],
                    "quantity": QUANTITY,
                    "product": PRODUCT
                })

                leg_detail = {
                    "symbol": symbol,
                    "option_type": cfg["option_type"],
                    "action": cfg["action"],
                    "quantity": QUANTITY,
                    "entry_price": ltp,
                    "product": PRODUCT
                }
                resolved_legs.append(leg_detail)

                # Only track short legs for SL/TP to prevent false exits
                if cfg["action"] == "SELL":
                    short_legs_for_tracker.append(leg_detail)
            else:
                self.logger.warning(f"Could not resolve {offset} {cfg['option_type']}")
                return

        if len(resolved_legs) != len(legs_config):
            self.logger.error("Failed to resolve all required legs.")
            return

        api_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=api_legs
            )

            if res.get("status") == "success":
                self.logger.info(f"Entry Order Success: {res}")

                self.all_open_legs = resolved_legs
                self.entry_time = datetime.now()

                entry_prices = [leg["entry_price"] for leg in short_legs_for_tracker]
                self.tracker.add_legs(short_legs_for_tracker, entry_prices, side="SELL")

                self.entered_today = True
                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def get_straddle_premium(self, chain):
        atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)
        if atm_item:
            ce_ltp = safe_float((atm_item.get("ce") or {}).get("ltp"))
            pe_ltp = safe_float((atm_item.get("pe") or {}).get("ltp"))
            return ce_ltp + pe_ltp
        return 0.0

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # 0. Daily Reset
                if datetime.now().date() != self.current_date:
                    self.entered_today = False
                    self.current_date = datetime.now().date()
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
                    time.sleep(60)
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
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # 4. Exit Management First
                if self.tracker.open_legs and self.all_open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Exit
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    eod_time = datetime.strptime(EXIT_TIME, "%H:%M").time()

                    if now.time() >= eod_time:
                        exit_now = True
                        exit_reason = "eod_sqoff"

                    # Max Hold Time explicitly calculated in case tracker misbehaves
                    if self.entry_time and not exit_now:
                        mins_held = (datetime.now() - self.entry_time).total_seconds() / 60
                        if mins_held >= MAX_HOLD_MIN:
                            exit_now = True
                            exit_reason = "time_stop"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                    straddle_premium = self.get_straddle_premium(chain)
                    self.logger.info(format_kv(
                        spot=f"{underlying_ltp:.2f}",
                        straddle=f"{straddle_premium:.2f}",
                        pos="OPEN"
                    ))

                # 5. Entry Logic
                if not self.tracker.open_legs and not self.entered_today:
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    start_time_dt = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
                    end_time_dt = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()

                    if start_time_dt <= now.time() <= end_time_dt:
                        if self.limiter.allow():
                            straddle_premium = self.get_straddle_premium(chain)

                            self.logger.info(format_kv(
                                spot=f"{underlying_ltp:.2f}",
                                straddle=f"{straddle_premium:.2f}",
                                pos="FLAT"
                            ))

                            should_enter = straddle_premium > MIN_STRADDLE_PREMIUM

                            if self.debouncer.edge("entry_signal", should_enter):
                                self._open_position(chain, straddle_premium)

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftyUltimateIronCondor()
    strategy.run()
