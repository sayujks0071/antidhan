#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if ATM straddle premium > 120. Sells OTM2, Buys OTM4.
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


class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"))
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Management Rules
        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

        # Time Constraints
        self.entry_start_time = os.getenv("ENTRY_START_TIME", "10:00")
        self.entry_end_time = os.getenv("ENTRY_END_TIME", "14:30")
        self.exit_time = os.getenv("EXIT_TIME", "15:15")

        # Premium Constraints
        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))

        # Rate Limiting & Cooldowns
        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "20"))
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.expiry = normalize_expiry(os.getenv("EXPIRY_DATE", ""))

        # State Tracking
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )

        self.last_expiry_check = 0
        self.entered_today = False
        self.current_date = datetime.now().date()
        self.all_open_legs = []  # Tracks all legs, while tracker holds only shorts

    def ensure_expiry(self):
        if self.expiry and (time.time() - self.last_expiry_check < self.expiry_refresh_sec):
            return

        self.logger.info("Fetching available expiry dates...")
        try:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
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

    def _close_position(self, exit_reason):
        """Close all open legs."""
        self.logger.info(f"Closing position. Reason: {exit_reason}")
        if not self.all_open_legs:
            return

        # Prepare exit legs (Reverse actions)
        legs_to_close = []
        for leg in self.all_open_legs:
            close_leg = {
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": "BUY" if leg["action"] == "SELL" else "SELL",
                "quantity": leg["quantity"],
                "product": leg.get("product", self.product)
            }
            legs_to_close.append(close_leg)

        # Sort: BUY actions (closing shorts) first
        legs_to_close.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            res = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.options_exchange,
                expiry_date=self.expiry,
                legs=legs_to_close
            )
            self.logger.info(f"event=trade Exit Order Response: {res}")

            if res.get("status") == "success":
                self.tracker.clear()
                self.all_open_legs = []
            else:
                self.logger.error(f"Exit failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _open_position(self, chain, straddle_premium):
        """Open Iron Condor position."""
        self.logger.info(f"Attempting to open Iron Condor position (Straddle: {straddle_premium:.2f})...")

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

            # Fallback logic if exact offset missing
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
                    "quantity": self.quantity,
                    "product": self.product
                })

                resolved_legs.append({
                    "symbol": symbol,
                    "option_type": cfg["option_type"],
                    "action": cfg["action"],
                    "quantity": self.quantity,
                    "entry_price": ltp,
                    "product": self.product
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
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.options_exchange,
                expiry_date=self.expiry,
                legs=api_legs
            )

            if res.get("status") == "success":
                self.logger.info(f"event=trade Entry Order Success: {res}")

                # We track all legs for exiting
                self.all_open_legs = resolved_legs

                # Add ONLY SHORT legs to Tracker to prevent false exits due to protective wings
                short_legs = [leg for leg in resolved_legs if leg["action"].upper() == "SELL"]
                entry_prices = [leg["entry_price"] for leg in short_legs]
                self.tracker.add_legs(short_legs, entry_prices, side="SELL")

                self.entered_today = True
                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} for {self.underlying} on {self.options_exchange}")

        while True:
            try:
                # Daily Reset
                if datetime.now().date() != self.current_date:
                    self.entered_today = False
                    self.current_date = datetime.now().date()
                    self.limiter = TradeLimiter(
                        max_per_day=self.max_orders_per_day,
                        max_per_hour=self.max_orders_per_hour,
                        cooldown_seconds=self.cooldown_seconds
                    )

                # Market Hours Check
                market_open = True
                try:
                    if not is_market_open():
                        market_open = False
                except:
                    pass

                if not market_open:
                    time.sleep(self.sleep_seconds)
                    continue

                # Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # Fetch Data
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count,
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=self.strike_count)
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # Exit Management (Priority)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Exit
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    eod_time = datetime.strptime(self.exit_time, "%H:%M").time()

                    if now.time() >= eod_time:
                        exit_now = True
                        exit_reason = "eod_sqoff"

                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue
                    else:
                        # Log status
                        self.logger.info(format_kv(
                            spot=f"{underlying_ltp:.2f}",
                            pos="OPEN",
                            pnl="RUNNING"
                        ))

                # Entry Logic
                if not self.tracker.open_legs and not self.entered_today:
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    start_time_dt = datetime.strptime(self.entry_start_time, "%H:%M").time()
                    end_time_dt = datetime.strptime(self.entry_end_time, "%H:%M").time()
                    can_trade_now = start_time_dt <= now.time() <= end_time_dt

                    # Calculate Straddle Premium
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

                    should_enter = (straddle_premium > self.min_straddle_premium)

                    # Edge detection combined with time check
                    if self.debouncer.edge("entry_signal", should_enter and can_trade_now):
                        if self.limiter.allow():
                            self._open_position(chain, straddle_premium)

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    strategy = NiftyIronCondorStrategy()
    strategy.run()
