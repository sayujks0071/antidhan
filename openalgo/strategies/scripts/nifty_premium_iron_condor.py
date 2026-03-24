#!/usr/bin/env python3
"""
Nifty Premium Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM if ATM straddle premium > 120. Sells OTM2, Buys OTM4 for protection.
Strict exit limits (40% SL, 50% TP, and 45-minute hold) on short legs.
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
root_dir = os.path.dirname(strategies_dir)

sys.path.insert(0, root_dir)
sys.path.insert(0, utils_dir)

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
    print(f"ERROR: Could not import strategy utilities. {e}", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# API Key retrieval
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

# ===========================
# CONFIGURATION
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyPremiumIronCondor")
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
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

class NiftyPremiumIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Tracker for short legs
        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.all_open_legs = [] # Track all legs for closure

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

    def ensure_expiry(self):
        """Refresh expiry date if needed."""
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

    def can_trade(self):
        """Check if trading is allowed based on time and daily limits."""
        ist_offset = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist_offset)

        # Parse times
        try:
            start_time = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
            exit_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
        except ValueError as e:
            self.logger.error(f"Error parsing time configuration: {e}")
            return False

        if not (start_time <= now.time() < exit_time):
            return False

        if self.entered_today:
            return False

        return True

    def _close_position(self, reason):
        """Close all open legs individually."""
        self.logger.info(f"Closing position. Reason: {reason}")
        if not self.all_open_legs:
            return

        # Prepare exit legs (Reverse actions)
        legs_to_close = []
        for leg in self.all_open_legs:
            close_leg = {
                "symbol": leg["symbol"],
                "action": "BUY" if leg["action"] == "SELL" else "SELL",
                "quantity": leg["quantity"],
                "product": leg.get("product", PRODUCT)
            }
            legs_to_close.append(close_leg)

        # Sort: BUY actions (closing shorts) first, then SELL actions (closing longs)
        legs_to_close.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        for close_leg in legs_to_close:
            try:
                # Use placesmartorder to close individual legs
                res = self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=close_leg["symbol"],
                    action=close_leg["action"],
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=close_leg["product"],
                    quantity=close_leg["quantity"],
                    position_size=0
                )
                self.logger.info(f"Trade response: Exit {close_leg['symbol']} {close_leg['action']} - {res}")
            except Exception as e:
                self.logger.error(f"Failed to close leg {close_leg['symbol']}: {e}")

        # Clear trackers
        self.tracker.clear()
        self.all_open_legs = []
        self.logger.info("Position completely closed.")

    def _open_position(self, chain, spot):
        """Open Iron Condor position."""
        self.logger.info("Attempting to open Iron Condor position...")

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
            # Find the item with the matching label
            for item in chain:
                opt = item.get(otype, {})
                if opt.get("label") == offset:
                    found_item = opt
                    break

            if found_item:
                symbol = found_item.get("symbol")
                ltp = safe_float(found_item.get("ltp"))

                api_legs.append({
                    "offset": offset,
                    "option_type": cfg["option_type"].upper(),
                    "action": cfg["action"],
                    "quantity": QUANTITY,
                    "product": PRODUCT
                })

                resolved_legs.append({
                    "symbol": symbol,
                    "option_type": cfg["option_type"].upper(),
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
                exchange=OPTIONS_EXCHANGE, # Use NFO here
                expiry_date=self.expiry,
                legs=api_legs
            )

            if res.get("status") == "success":
                self.logger.info(f"Entry Order Success: {res}")

                # Add ONLY SELL legs to the tracker to avoid false positive exits on long legs
                sell_legs = [leg for leg in resolved_legs if leg["action"] == "SELL"]
                sell_entry_prices = [leg["entry_price"] for leg in sell_legs]
                self.tracker.add_legs(sell_legs, sell_entry_prices, side="SELL")

                # Store all open legs for eventual closure
                self.all_open_legs = resolved_legs

                self.entered_today = True
                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING}")

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
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Exit
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    eod_time = datetime.strptime(EXIT_TIME, "%H:%M").time()

                    if now.time() >= eod_time:
                        exit_now = True
                        exit_reason = "eod_sqoff"

                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue
                    else:
                        self.logger.info(format_kv(
                            spot=f"{underlying_ltp:.2f}",
                            pos="OPEN",
                            status="MONITORING"
                        ))

                # 5. Entry Logic
                if not self.all_open_legs and self.can_trade() and self.limiter.allow():
                    # Check straddle premium
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

                    should_enter = straddle_premium > MIN_STRADDLE_PREMIUM

                    if self.debouncer.edge("entry_signal", should_enter):
                        self._open_position(chain, underlying_ltp)

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftyPremiumIronCondorStrategy()
    strategy.run()