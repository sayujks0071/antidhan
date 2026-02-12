#!/usr/bin/env python3
"""
SensexWeeklySmartIronCondor - SENSEX Weekly Options (OpenAlgo Web UI Compatible)
Smart Iron Condor strategy optimized for SENSEX weekly options on BSE (BFO).

Exchange: BFO (BSE F&O)
Underlying: SENSEX on BSE_INDEX
Expiry: Weekly Friday
Logic: Sell OTM2 Strangle + Buy OTM4 Wings (Iron Condor). Enters on high IV (straddle premium).
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
    from strategy_common import (
        SignalDebouncer,
        TradeLedger,
        TradeLimiter,
        format_kv,
        DataFreshnessGuard,
        RiskConfig,
        RiskManager,
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
# CONFIGURATION - SENSEX WEEKLY OPTIONS
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "sensex_weekly_smart_ic")
UNDERLYING = os.getenv("UNDERLYING", "SENSEX")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "BSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "BFO")
PRODUCT = os.getenv("PRODUCT", "MIS")           # MIS=Intraday, NRML=Positional
QUANTITY = int(os.getenv("QUANTITY", "1"))        # 1 lot = 10 units for SENSEX
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "12"))

# Strategy-specific parameters
MIN_STRADDLE_PREMIUM = float(os.getenv("MIN_STRADDLE_PREMIUM", "400"))
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "10:00")
FRIDAY_EXIT_TIME = os.getenv("FRIDAY_EXIT_TIME", "14:00")
NORMAL_EXIT_TIME = os.getenv("NORMAL_EXIT_TIME", "15:15")

# Risk parameters
SL_PCT = float(os.getenv("SL_PCT", "30"))        # % of entry premium
TP_PCT = float(os.getenv("TP_PCT", "40"))         # % of entry premium
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "30"))

# Rate limiting
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "20"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "6"))

# Manual expiry override (format: 14FEB26)
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

# Defensive normalization: SENSEX/BANKEX trade on BSE
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and UNDERLYING_EXCHANGE.upper() == "NSE_INDEX":
    UNDERLYING_EXCHANGE = "BSE_INDEX"
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and OPTIONS_EXCHANGE.upper() == "NFO":
    OPTIONS_EXCHANGE = "BFO"

# API Key retrieval (MANDATORY)
API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

if not API_KEY:
    try:
        # Fallback to database if available in environment
        from database.auth_db import get_first_available_api_key
        API_KEY = get_first_available_api_key()
        if API_KEY:
            print("Successfully retrieved API Key from database.", flush=True)
    except Exception as e:
        print(f"Warning: Could not retrieve API key from database: {e}", flush=True)

if not API_KEY:
    raise ValueError("API Key must be set in OPENALGO_APIKEY environment variable")


class SensexWeeklySmartIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )

        # Ledger setup
        ledger_dir = os.path.join(os.path.dirname(strategies_dir), "log", "strategies", "trades")
        ledger_path = os.path.join(ledger_dir, f"{STRATEGY_NAME}_{UNDERLYING}_trades.csv")
        self.ledger = TradeLedger(ledger_path)

        self.expiry = EXPIRY_DATE
        self.last_expiry_check = 0
        self.entered_today = False
        self.current_date = datetime.now().date()

    def _get_atm_strike(self, chain):
        """Finds ATM strike from chain data."""
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return item["strike"]
        return None

    def _calculate_straddle_premium(self, chain, atm_strike):
        """Calculates combined premium of ATM CE and PE."""
        ce_ltp = 0.0
        pe_ltp = 0.0

        for item in chain:
            if item["strike"] == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                break

        return ce_ltp + pe_ltp

    def ensure_expiry(self):
        """Refreshes expiry date if needed."""
        now = time.time()
        if self.expiry and (now - self.last_expiry_check < EXPIRY_REFRESH_SEC):
            return

        # If manual expiry is set, just normalize and use it
        if EXPIRY_DATE:
            self.expiry = normalize_expiry(EXPIRY_DATE)
            return

        # Fetch available expiries
        resp = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
        if resp.get("status") == "success":
            dates = resp.get("data", [])
            nearest = choose_nearest_expiry(dates)
            if nearest:
                self.expiry = nearest
                self.logger.info(f"Selected Expiry: {self.expiry}")
            else:
                self.logger.warning("No valid future expiry found.")
        else:
            self.logger.error(f"Failed to fetch expiry: {resp.get('message')}")

        self.last_expiry_check = now

    def _get_time_check(self):
        """Checks if current time is within allowed trading window."""
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")

        # Basic Market Hours
        if not is_market_open():
            return False, "market_closed"

        # Strategy Start Time
        if current_time_str < ENTRY_START_TIME:
            return False, "before_start_time"

        # Friday Special Exit
        is_friday = (now.weekday() == 4)
        exit_cutoff = FRIDAY_EXIT_TIME if is_friday else NORMAL_EXIT_TIME

        if current_time_str >= exit_cutoff:
            return False, "after_cutoff_time"

        return True, "ok"

    def _close_position(self, chain, reason):
        """Closes all open legs."""
        if not self.tracker.open_legs:
            return

        self.logger.info(f"Closing position. Reason: {reason}")

        # Reverse actions: SELL -> BUY, BUY -> SELL
        closing_legs = []

        for leg in self.tracker.open_legs:
            action = leg["action"].upper()
            reverse_action = "BUY" if action == "SELL" else "SELL"

            closing_leg = {
                "symbol": leg["symbol"],
                "action": reverse_action,
                "quantity": leg["quantity"],
                "product": PRODUCT,
                "option_type": leg.get("option_type", "CE"),
                "offset": "EXIT"
            }
            closing_legs.append(closing_leg)

        # Sort: BUYs first (to cover shorts/close longs safely)
        closing_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        # Execute
        try:
            resp = self.client.optionsmultiorder(
                strategy=f"{STRATEGY_NAME}_exit",
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=closing_legs
            )

            if resp.get("status") == "success":
                self.logger.info(f"Exit Order Placed: {resp.get('message')}")
                self.ledger.append({
                    "timestamp": datetime.now().isoformat(),
                    "side": "EXIT",
                    "reason": reason,
                    "details": str(resp)
                })
                self.tracker.clear()
            else:
                self.logger.error(f"Exit Order Failed: {resp.get('message')}")

        except Exception as e:
            self.logger.error(f"Exception during exit: {e}")

    def _open_position(self, chain, reason):
        """Opens the Iron Condor position."""
        if not self.limiter.allow():
            self.logger.info("Trade limiter preventing entry.")
            return

        atm_strike = self._get_atm_strike(chain)
        if not atm_strike:
            self.logger.error("Could not determine ATM strike.")
            return

        # Find strikes: OTM2 (Short) and OTM4 (Long)
        # SENSEX strike interval is 100.
        strike_interval = 100

        short_ce_strike = atm_strike + (2 * strike_interval)
        long_ce_strike = atm_strike + (4 * strike_interval)

        short_pe_strike = atm_strike - (2 * strike_interval)
        long_pe_strike = atm_strike - (4 * strike_interval)

        # Construct legs
        legs = [
            # Wings (Protection) - BUY first for margin benefit
            {"strike": long_ce_strike, "option_type": "CE", "action": "BUY", "offset": "OTM4"},
            {"strike": long_pe_strike, "option_type": "PE", "action": "BUY", "offset": "OTM4"},
            # Body (Premium) - SELL
            {"strike": short_ce_strike, "option_type": "CE", "action": "SELL", "offset": "OTM2"},
            {"strike": short_pe_strike, "option_type": "PE", "action": "SELL", "offset": "OTM2"},
        ]

        # Map to symbols and get LTPs for tracker
        formatted_legs = []
        tracker_legs = []
        tracker_prices = []

        # Helper to find item in chain
        def find_item(s, otype):
            for item in chain:
                if item["strike"] == s:
                    return item.get(otype.lower(), {})
            return {}

        for leg in legs:
            item = find_item(leg["strike"], leg["option_type"])
            symbol = item.get("symbol")
            ltp = safe_float(item.get("ltp"))

            if not symbol:
                self.logger.warning(f"Could not find symbol for strike {leg['strike']} {leg['option_type']}")
                return

            formatted_legs.append({
                "symbol": symbol,
                "offset": leg["offset"],
                "option_type": leg["option_type"],
                "action": leg["action"],
                "quantity": QUANTITY,
                "product": PRODUCT
            })

            # For tracker
            tracker_legs.append({
                "symbol": symbol,
                "action": leg["action"],
                "quantity": QUANTITY,
                "option_type": leg["option_type"]
            })
            tracker_prices.append(ltp)

        self.logger.info(f"Placing Order: {formatted_legs}")

        try:
            resp = self.client.optionsmultiorder(
                strategy=f"{STRATEGY_NAME}_entry",
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=formatted_legs
            )

            if resp.get("status") == "success":
                self.logger.info(f"Entry Order Placed: {resp.get('message')}")
                # Register with tracker
                self.tracker.add_legs(tracker_legs, tracker_prices, side="SELL") # Net Credit
                self.entered_today = True
                self.limiter.record()

                self.ledger.append({
                    "timestamp": datetime.now().isoformat(),
                    "side": "ENTRY",
                    "reason": reason,
                    "details": str(resp)
                })
            else:
                self.logger.error(f"Entry Order Failed: {resp.get('message')}")

        except Exception as e:
            self.logger.error(f"Exception during entry: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # 0. Daily Reset
                if datetime.now().date() != self.current_date:
                    self.entered_today = False
                    self.current_date = datetime.now().date()
                    self.logger.info("New day detected. Resetting daily flags.")

                # 1. Market & Time Check
                can_trade, msg = self._get_time_check()
                if not can_trade and not self.tracker.open_legs:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 2. Expiry
                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No expiry available.")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Data Fetch
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
                atm_strike = self._get_atm_strike(chain)
                straddle_premium = self._calculate_straddle_premium(chain, atm_strike) if atm_strike else 0

                # 4. EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if not can_trade:
                        exit_now = True
                        exit_reason = f"force_exit_{msg}"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # 5. LOG STATUS
                pnl_info = "FLAT"
                if self.tracker.open_legs:
                    pnl_info = "OPEN"

                self.logger.info(format_kv(
                    spot=f"{underlying_ltp:.2f}",
                    atm=atm_strike,
                    straddle=f"{straddle_premium:.2f}",
                    expiry=self.expiry,
                    pos=pnl_info,
                    entered=self.entered_today
                ))

                # 6. ENTRY LOGIC
                if (not self.tracker.open_legs
                    and not self.entered_today
                    and can_trade
                    and self.limiter.allow()):

                    # Condition: Straddle Premium > MIN (IV Check)
                    iv_condition = straddle_premium >= MIN_STRADDLE_PREMIUM

                    if self.debouncer.edge("entry_signal", iv_condition):
                        self.logger.info(f"Entry Signal! Straddle {straddle_premium:.2f} >= {MIN_STRADDLE_PREMIUM}")
                        self._open_position(chain, "high_premium_entry")

            except Exception as e:
                self.logger.error(f"Main Loop Error: {e}", exc_info=True)
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    SensexWeeklySmartIronCondor().run()
