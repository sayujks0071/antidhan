#!/usr/bin/env python3
"""
SensexWeeklyIC - SENSEX Weekly Iron Condor Strategy (OpenAlgo Web UI Compatible)
Sells OTM2 CE/PE and Buys OTM4 CE/PE on SENSEX (BFO) for weekly income.

Exchange: BFO (BSE F&O)
Underlying: SENSEX on BSE_INDEX
Expiry: Weekly Friday
Logic: Delta neutral income generation with defined risk wings.
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

# Import Utilities with Fallback
try:
    # Try importing trading_utils first
    from trading_utils import is_market_open
except ImportError:
    # Fallback if trading_utils fails (e.g., missing httpx)
    print("Warning: trading_utils import failed. Using local is_market_open.", flush=True)

    def is_market_open():
        """Check if market is open (09:15 - 15:30 IST)."""
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)
        if now.weekday() >= 5:  # Saturday/Sunday
            return False
        return now.time() >= datetime.strptime("09:15", "%H:%M").time() and \
               now.time() <= datetime.strptime("15:30", "%H:%M").time()

try:
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        safe_float,
        safe_int,
    )
    from strategy_common import (
        SignalDebouncer,
        TradeLimiter,
        format_kv,
    )
except ImportError as e:
    print(f"ERROR: Could not import strategy utilities: {e}", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# ===========================
# API KEY RETRIEVAL
# ===========================
API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

if not API_KEY:
    try:
        # Attempt to get API key from database if env var missing
        from database.auth_db import get_first_available_api_key
        API_KEY = get_first_available_api_key()
        if API_KEY:
            print("Successfully retrieved API Key from database.", flush=True)
    except Exception as e:
        print(f"Warning: Could not retrieve API key from database: {e}", flush=True)

if not API_KEY:
    raise ValueError("API Key must be set in OPENALGO_APIKEY environment variable")


# ===========================
# CONFIGURATION - SENSEX WEEKLY IRON CONDOR
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "sensex_weekly_ic")
UNDERLYING = os.getenv("UNDERLYING", "SENSEX")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "BSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "BFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = int(os.getenv("QUANTITY", "1"))        # 1 lot = 10 units
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "12"))

# Strategy Parameters
SELL_OFFSET = os.getenv("SELL_OFFSET", "OTM2")    # Sell strikes
BUY_OFFSET = os.getenv("BUY_OFFSET", "OTM4")      # Buy wings
MIN_STRADDLE_PREMIUM = float(os.getenv("MIN_STRADDLE_PREMIUM", "400"))
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "10:00")

# Risk Parameters
SL_PCT = float(os.getenv("SL_PCT", "35"))         # % of Net Credit
TP_PCT = float(os.getenv("TP_PCT", "45"))         # % of Net Credit
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))

# Rate Limiting
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "20"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "6"))

# Manual Expiry Override
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

# Defensive Normalization
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and UNDERLYING_EXCHANGE.upper() == "NSE_INDEX":
    UNDERLYING_EXCHANGE = "BSE_INDEX"
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and OPTIONS_EXCHANGE.upper() == "NFO":
    OPTIONS_EXCHANGE = "BFO"


class SensexWeeklyStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        # Initialize tracker with wide limits as we handle PnL manually for Net Credit logic
        self.tracker = OptionPositionTracker(sl_pct=999, tp_pct=999, max_hold_min=MAX_HOLD_MIN)
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.expiry = EXPIRY_DATE
        self.last_expiry_check = 0
        self.entered_today = False

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

    def get_net_pnl_pct(self, chain):
        """
        Calculate PnL % based on Net Credit.
        PnL = Net Credit - Current Cost to Close
        """
        if not self.tracker.open_legs:
            return 0.0

        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        net_credit = 0.0
        current_cost = 0.0

        for leg in self.tracker.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            curr = ltp_map.get(sym, entry)  # Fallback to entry if LTP missing
            action = leg["action"].upper()

            if action == "SELL":
                net_credit += entry
                current_cost += curr
            else:  # BUY
                net_credit -= entry
                current_cost -= curr

        # If net credit is zero or negative (debit), this logic needs adjustment.
        # Iron Condor should be net credit.
        if net_credit <= 0:
            return 0.0

        pnl = net_credit - current_cost
        pnl_pct = (pnl / net_credit) * 100
        return pnl_pct

    def check_exit(self, chain):
        """Check exit conditions: SL, TP, Time, EOD."""
        if not self.tracker.open_legs:
            return

        # 1. Time Stop (handled by tracker mostly, but we double check)
        exit_now, legs, reason = self.tracker.should_exit(chain)
        if exit_now and reason == "time_stop":
            self.logger.info(f"Time stop triggered: {reason}")
            self._close_position(chain, reason)
            return

        # 2. Net Credit PnL Check
        pnl_pct = self.get_net_pnl_pct(chain)

        if pnl_pct <= -SL_PCT:
            self.logger.info(f"Stop Loss Hit: {pnl_pct:.2f}% (Limit: -{SL_PCT}%)")
            self._close_position(chain, "stop_loss")
            return

        if pnl_pct >= TP_PCT:
            self.logger.info(f"Take Profit Hit: {pnl_pct:.2f}% (Limit: +{TP_PCT}%)")
            self._close_position(chain, "take_profit")
            return

        # 3. Friday Expiry Logic (Exit by 14:00)
        # Check if today is Friday (weekday=4)
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)
        if now.weekday() == 4 and now.time() >= datetime.strptime("14:00", "%H:%M").time():
            self.logger.info("Friday Expiry 2 PM Exit Rule triggered.")
            self._close_position(chain, "friday_expiry_exit")
            return

        # 4. EOD Square-off (15:15)
        if now.time() >= datetime.strptime("15:15", "%H:%M").time():
            self.logger.info("EOD Square-off triggered.")
            self._close_position(chain, "eod_exit")
            return

        self.logger.info(f"Position Status: PnL={pnl_pct:.2f}%")

    def _close_position(self, chain, reason):
        """Close all open legs."""
        self.logger.info(f"Closing position. Reason: {reason}")

        # Sort legs to buy back shorts first (margin safety)
        # However, for closing:
        # If we are Short, we BUY to close.
        # If we are Long, we SELL to close.
        # Generally, close Shorts first to release margin? Or Longs first?
        # OpenAlgo placesmartorder/optionsmultiorder handles order, but if we send a list:
        # Closing Short (BUY) reduces margin usage.
        # Closing Long (SELL) increases margin usage (if it was a hedge).
        # So we should CLOSE SHORTS FIRST.

        legs_to_close = []
        for leg in self.tracker.open_legs:
            close_leg = leg.copy()
            close_leg["action"] = "BUY" if leg["action"] == "SELL" else "SELL"
            legs_to_close.append(close_leg)

        # Sort: BUY actions (closing shorts) first
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
            self.tracker.clear()
        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _open_position(self, chain):
        """Open Iron Condor Position."""
        self.logger.info("Attempting to open Iron Condor...")

        # Identify Strikes
        atm_item = next((x for x in chain if (x.get("ce") or {}).get("label") == "ATM"), None)
        if not atm_item:
            self.logger.warning("ATM strike not found.")
            return

        # Build Legs
        legs = [
            {"offset": BUY_OFFSET, "option_type": "CE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
            {"offset": BUY_OFFSET, "option_type": "PE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
            {"offset": SELL_OFFSET, "option_type": "CE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
            {"offset": SELL_OFFSET, "option_type": "PE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
        ]

        # BUY legs first for margin benefit
        # optionsmultiorder usually executes sequentially
        # Sort legs: BUY first
        legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=legs
            )

            if res.get("status") == "success":
                self.logger.info(f"Entry Order Success: {res}")
                # We need entry prices to track PnL.
                # In a real scenario, we'd fetch orderbook. Here we estimate from Chain LTP.
                # Or wait for positionbook update.
                # For simplicity, we use current Chain LTPs as "Entry Price" approximation
                # if the API doesn't return fill prices immediately.

                # Resolve symbols and entry prices from offsets
                resolved_legs = []
                entry_prices = []

                for leg in legs:
                    offset = leg["offset"]
                    option_type = leg["option_type"]

                    found = False
                    for item in chain:
                        opt = item.get(option_type.lower(), {})
                        if opt.get("label") == offset:
                            leg_update = leg.copy()
                            leg_update["symbol"] = opt.get("symbol")
                            resolved_legs.append(leg_update)
                            entry_prices.append(safe_float(opt.get("ltp")))
                            found = True
                            break
                    if not found:
                        self.logger.warning(f"Could not resolve symbol for {offset} {option_type}")

                if len(resolved_legs) == 4:
                    self.tracker.add_legs(resolved_legs, entry_prices, side="SELL") # Net Credit
                    self.entered_today = True
                    self.limiter.record()
                else:
                    self.logger.error("Failed to resolve all legs for tracker.")
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # 1. Market Hours Check
                if not is_market_open():
                    self.entered_today = False  # Reset for new day
                    self.logger.info("Market closed. Sleeping...")
                    time.sleep(60)
                    continue

                # 2. Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No expiry available.")
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

                # 4. Exit Management
                self.check_exit(chain)

                # 5. Entry Logic
                # Skip if already in position or max orders reached or already entered today (if intended)
                # The prompt example said "Only one trade per day" in one example, but "max_per_day=20" in config.
                # We'll use the Limiter.

                if self.tracker.open_legs:
                    time.sleep(SLEEP_SECONDS)
                    continue

                if not self.limiter.allow():
                    time.sleep(SLEEP_SECONDS)
                    continue

                # Check Entry Time (e.g. > 10:00)
                ist = timezone(timedelta(hours=5, minutes=30))
                now = datetime.now(ist)
                start_time_dt = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()

                if now.time() < start_time_dt:
                    # Too early
                    time.sleep(SLEEP_SECONDS)
                    continue

                # Check Straddle Premium
                atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)
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

                    # Debounce Signal
                    if self.debouncer.edge("entry_signal", should_enter):
                        self._open_position(chain)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = SensexWeeklyStrategy()
    strategy.run()
