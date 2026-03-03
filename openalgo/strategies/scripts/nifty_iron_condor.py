#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120, sells OTM2 CE/PE, buys OTM4 CE/PE.
"""
import os
import sys
import time
from datetime import datetime, timedelta

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
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"), default=1)
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"), default=12)

SL_PCT = safe_float(os.getenv("SL_PCT", "40.0"), default=40.0)
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"), default=50.0)
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"), default=45)

COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "120"), default=120)
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "30"), default=30)
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), default=3600)
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), default=1)
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), default=1)

# Entry requirements
MIN_STRADDLE_PREMIUM = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"), default=120.0)
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "10:00")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")
EXPIRY_DATE_OVERRIDE = os.getenv("EXPIRY_DATE", None)


class NiftyIronCondorStrategy:
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

        self.entered_today = False
        self.current_date = datetime.now().date()
        self.expiry = normalize_expiry(EXPIRY_DATE_OVERRIDE)
        self.last_expiry_refresh = 0

    def ensure_expiry(self):
        if EXPIRY_DATE_OVERRIDE:
            self.expiry = normalize_expiry(EXPIRY_DATE_OVERRIDE)
            return

        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > EXPIRY_REFRESH_SEC):
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved Expiry: {self.expiry}")
            else:
                self.logger.warning(f"Failed to fetch expiry dates: {res}")

    def _close_position(self, chain, exit_reason):
        """Close an open position by reversing the legs."""
        self.logger.info(f"Closing position. Reason: {exit_reason}")

        if not self.tracker.open_legs:
            return

        legs_to_close = []
        for leg in self.tracker.open_legs:
            # Reverse the action
            close_action = "SELL" if leg["action"] == "BUY" else "BUY"

            legs_to_close.append({
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": close_action,
                "quantity": leg["quantity"],
                "product": leg["product"]
            })

        # Sort API legs: BUY actions (closing shorts) first for margin benefit
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
            else:
                self.logger.error(f"Exit failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _open_position(self, chain, reason):
        """Open the Iron Condor position."""
        self.logger.info(f"Attempting to open Iron Condor position ({reason})...")

        # Iron Condor: Sell OTM2 Strangle, Buy OTM4 Wings
        legs_config = [
            {"offset": "OTM4", "option_type": "CE", "action": "BUY"},
            {"offset": "OTM4", "option_type": "PE", "action": "BUY"},
            {"offset": "OTM2", "option_type": "CE", "action": "SELL"},
            {"offset": "OTM2", "option_type": "PE", "action": "SELL"},
        ]

        resolved_legs = []
        api_legs = []

        # Resolve symbols locally
        for cfg in legs_config:
            offset = cfg["offset"]
            otype = cfg["option_type"].lower()

            found_item = None
            for item in chain:
                opt = item.get(otype, {})
                if opt.get("label") == offset:
                    found_item = opt
                    break

            # Fallback logic if exact offset missing (e.g., trying OTM3 if OTM4 missing)
            if not found_item and offset == "OTM4":
                 for item in chain:
                    opt = item.get(otype, {})
                    if opt.get("label") == "OTM3":
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

        # Sort API legs: BUY first for margin benefit
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

                # Add to Tracker
                entry_prices = [leg["entry_price"] for leg in resolved_legs]
                self.tracker.add_legs(resolved_legs, entry_prices, side="SELL")

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

                # 4. Exit Management (Priority)
                now_dt = datetime.now()
                eod_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
                is_eod = now_dt.time() >= eod_time

                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if is_eod:
                        exit_now = True
                        exit_reason = "eod_sqoff"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue
                    else:
                        # Log status
                        self.logger.info(format_kv(
                            spot=f"{underlying_ltp:.2f}",
                            pos="OPEN",
                            pnl="RUNNING"
                        ))

                # 5. Entry Logic
                if not self.tracker.open_legs and not self.entered_today and not is_eod:
                    start_time_dt = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()

                    if now_dt.time() >= start_time_dt:
                        if self.limiter.allow():
                            # Straddle Premium Check
                            atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)
                            straddle_premium = 0.0
                            if atm_item:
                                ce_ltp = safe_float((atm_item.get("ce") or {}).get("ltp"))
                                pe_ltp = safe_float((atm_item.get("pe") or {}).get("ltp"))
                                straddle_premium = ce_ltp + pe_ltp

                            self.logger.info(format_kv(
                                spot=f"{underlying_ltp:.2f}",
                                straddle=f"{straddle_premium:.2f}",
                                pos="FLAT"
                            ))

                            should_enter = (straddle_premium > MIN_STRADDLE_PREMIUM)

                            if self.debouncer.edge("entry_signal", should_enter):
                                self._open_position(chain, f"straddle_premium_{straddle_premium:.2f}")

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftyIronCondorStrategy()
    strategy.run()
