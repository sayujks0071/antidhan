#!/usr/bin/env python3
"""
SENSEX Weekly Income Strategy - Production Iron Condor (OpenAlgo Compatible)
Implements a robust Iron Condor strategy on SENSEX weekly options with Net Credit PnL tracking and Friday expiry handling.

Exchange: BFO (BSE F&O)
Underlying: SENSEX on BSE_INDEX
Expiry: Weekly Friday
Logic: Sell OTM2 Strangle, Buy OTM4 Wings. Entry > 10:00 AM if Straddle Premium > 400.
Risk: SL 30% of Net Credit, TP 50% of Net Credit. Force exit Friday 14:00.
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
utils_dir = os.path.join(script_dir, "utils")
sys.path.insert(0, utils_dir)

try:
    from optionchain_utils import (
        OptionChainClient,
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
    )
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# ===========================
# API KEY SETUP
# ===========================
API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

root_dir = os.path.dirname(script_dir)
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


# ===========================
# CONFIGURATION - SENSEX WEEKLY OPTIONS
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "sensex_weekly_income")
UNDERLYING = os.getenv("UNDERLYING", "SENSEX")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "BSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "BFO")
PRODUCT = os.getenv("PRODUCT", "MIS")           # MIS=Intraday
QUANTITY = int(os.getenv("QUANTITY", "1"))        # 1 lot = 10 units for SENSEX
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "15"))

# Strategy Parameters
MIN_STRADDLE_PREMIUM = float(os.getenv("MIN_STRADDLE_PREMIUM", "400"))
# Iron Condor offsets: Sell OTM2, Buy OTM4
SHORT_OFFSET = os.getenv("SHORT_OFFSET", "OTM2")
LONG_OFFSET = os.getenv("LONG_OFFSET", "OTM4")

# Risk parameters (Percentage of NET CREDIT)
SL_PCT = float(os.getenv("SL_PCT", "30"))        # 30% of Net Credit
TP_PCT = float(os.getenv("TP_PCT", "50"))         # 50% of Net Credit
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "60"))

# Rate limiting
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "180"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "5"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

# Manual expiry override (format: 14FEB26)
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

# Defensive normalization: SENSEX/BANKEX trade on BSE
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and UNDERLYING_EXCHANGE.upper() == "NSE_INDEX":
    UNDERLYING_EXCHANGE = "BSE_INDEX"
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and OPTIONS_EXCHANGE.upper() == "NFO":
    OPTIONS_EXCHANGE = "BFO"


# ===========================
# LOCAL UTILITIES
# ===========================

def is_market_open_local():
    """
    Checks if Indian market is open (09:15 - 15:30 IST) using UTC time.
    Avoids reliance on external libs like httpx or pytz.
    """
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now + timedelta(hours=5, minutes=30)

    # Weekends check
    if ist_now.weekday() >= 5:
        return False

    # Time check (9:15 to 15:30)
    current_time = ist_now.time()
    market_open = datetime.strptime("09:15", "%H:%M").time()
    market_close = datetime.strptime("15:30", "%H:%M").time()

    return market_open <= current_time <= market_close

class NetCreditPositionTracker:
    """
    Tracks PnL based on Net Credit collected (Sell Premium - Buy Premium).
    Ideal for Iron Condors and Credit Spreads.
    """
    def __init__(self, sl_pct, tp_pct, max_hold_min):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min
        self.open_legs = []
        self.entry_time = None
        self.net_credit_collected = 0.0

    def add_legs(self, legs, entry_prices):
        """
        Registers position legs and calculates initial Net Credit.
        """
        self.open_legs = []
        self.entry_time = datetime.now()
        self.net_credit_collected = 0.0

        for i, leg in enumerate(legs):
            leg_data = leg.copy()
            entry_price = safe_float(entry_prices[i])
            leg_data["entry_price"] = entry_price
            self.open_legs.append(leg_data)

            # Calculate Net Credit
            # SELL adds to credit, BUY subtracts from credit
            if leg["action"].upper() == "SELL":
                self.net_credit_collected += entry_price
            else:
                self.net_credit_collected -= entry_price

        print(f"Position Entered. Net Credit: {self.net_credit_collected:.2f}", flush=True)

    def should_exit(self, chain):
        """
        Calculates current cost to close and compares with Net Credit.
        Returns: (bool exit_now, list legs, string exit_reason)
        """
        if not self.open_legs:
            return False, [], ""

        # 1. Time Stop
        minutes_held = (datetime.now() - self.entry_time).total_seconds() / 60
        if minutes_held >= self.max_hold_min:
            return True, self.open_legs, f"time_stop_({int(minutes_held)}m)"

        # 2. PnL Calculation (Net Credit Basis)
        # Current Value to Close = Buy back shorts + Sell longs
        # Cost to Close = (Current Price of Shorts) - (Current Price of Longs)

        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        current_cost_to_close = 0.0

        for leg in self.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            curr = ltp_map.get(sym, entry) # Fallback to entry if data missing (neutral impact)

            if leg["action"].upper() == "SELL":
                # To close a SHORT, we BUY it back (Cost)
                current_cost_to_close += curr
            else:
                # To close a LONG, we SELL it (Credit/Negative Cost)
                current_cost_to_close -= curr

        # PnL = Net Credit Collected - Current Cost to Close
        pnl = self.net_credit_collected - current_cost_to_close

        # PnL % = PnL / Net Credit Collected * 100
        # If Net Credit is 0 or negative (Debit), this logic needs inversion,
        # but for Iron Condor it should be positive.
        if self.net_credit_collected <= 0:
            # Fallback for Debit strategies if reused accidentally
            pnl_pct = 0
        else:
            pnl_pct = (pnl / self.net_credit_collected) * 100

        # Check Stops
        # SL: Loss of X% of Credit. e.g. Collected 100. SL 30%. Loss = -30. PnL <= -30.
        if pnl_pct <= -self.sl_pct:
            return True, self.open_legs, f"stop_loss_({pnl_pct:.1f}%)"

        # TP: Profit of X% of Credit. e.g. Collected 100. TP 50%. Profit = 50. PnL >= 50.
        if pnl_pct >= self.tp_pct:
            return True, self.open_legs, f"take_profit_({pnl_pct:.1f}%)"

        return False, [], ""

    def clear(self):
        self.open_legs = []
        self.entry_time = None
        self.net_credit_collected = 0.0


# ===========================
# STRATEGY LOGIC
# ===========================

class SensexWeeklyStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = NetCreditPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )

        self.expiry = EXPIRY_DATE
        self.last_expiry_check = 0
        self.entered_today = False  # To enforce STRICT one trade per day if needed, or just track state
        self.last_entry_date = None

    def ensure_expiry(self):
        """Resolves or refreshes the nearest expiry date."""
        if EXPIRY_DATE:
            self.expiry = EXPIRY_DATE
            return

        if time.time() - self.last_expiry_check < EXPIRY_REFRESH_SEC and self.expiry:
            return

        try:
            resp = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE)
            if resp.get("status") == "success":
                dates = resp.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.logger.info(f"Resolved Expiry: {self.expiry}")
                    self.last_expiry_check = time.time()
                else:
                    self.logger.warning("No future expiry found.")
        except Exception as e:
            self.logger.error(f"Expiry fetch failed: {e}")

    def get_ist_time(self):
        return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

    def is_friday_expiry(self):
        """Checks if today is Friday and matches the expiry date."""
        if not self.expiry:
            return False

        ist_now = self.get_ist_time()
        today_str = ist_now.strftime("%d%b%y").upper()

        # Check if today is Friday (4)
        if ist_now.weekday() == 4:
            # Check if today is the expiry date
            # Normalization might be needed if format differs, but usually DDMMMYY matches
            if today_str == self.expiry.upper():
                return True
        return False

    def can_trade(self):
        """Checks time windows and limits."""
        ist_now = self.get_ist_time()
        current_time = ist_now.time()

        # 1. Time Window: 10:00 AM to 02:30 PM
        start_time = datetime.strptime("10:00", "%H:%M").time()
        end_time = datetime.strptime("14:30", "%H:%M").time()

        if not (start_time <= current_time <= end_time):
            return False

        # 2. Friday Special: No new entries after 1:00 PM on expiry day
        if self.is_friday_expiry():
            friday_cutoff = datetime.strptime("13:00", "%H:%M").time()
            if current_time > friday_cutoff:
                return False

        # 3. Rate Limits
        if not self.limiter.allow():
            return False

        return True

    def find_legs(self, chain):
        """
        Identifies OTM2 and OTM4 strikes for Iron Condor.
        Returns list of leg dictionaries.
        """
        # Sort chain by strike
        sorted_chain = sorted(chain, key=lambda x: x["strike"])

        atm_item = next((item for item in sorted_chain if item.get("ce", {}).get("label") == "ATM"), None)
        if not atm_item:
            return None

        atm_index = sorted_chain.index(atm_item)

        # Helper to get strike at offset
        def get_strike_at_offset(index, offset_str, direction):
            # Parse offset like "OTM2" -> 2
            try:
                steps = int(offset_str.replace("OTM", "").replace("ITM", "").replace("ATM", "0") or 0)
            except:
                steps = 2 # default

            if direction == "CE": # OTM is Higher Strike
                target_idx = index + steps
            else: # PE: OTM is Lower Strike
                target_idx = index - steps

            if 0 <= target_idx < len(sorted_chain):
                return sorted_chain[target_idx]
            return None

        # Short Legs (OTM2)
        short_ce_item = get_strike_at_offset(atm_index, SHORT_OFFSET, "CE")
        short_pe_item = get_strike_at_offset(atm_index, SHORT_OFFSET, "PE")

        # Long Legs (OTM4) - Wings
        long_ce_item = get_strike_at_offset(atm_index, LONG_OFFSET, "CE")
        long_pe_item = get_strike_at_offset(atm_index, LONG_OFFSET, "PE")

        if not (short_ce_item and short_pe_item and long_ce_item and long_pe_item):
            return None

        # Construct Legs: Buy Wings First (Margin Benefit), Then Sell Inner
        legs = []

        # Long Wings
        legs.append({"symbol": long_ce_item["ce"]["symbol"], "action": "BUY", "option_type": "CE", "quantity": QUANTITY, "product": PRODUCT})
        legs.append({"symbol": long_pe_item["pe"]["symbol"], "action": "BUY", "option_type": "PE", "quantity": QUANTITY, "product": PRODUCT})

        # Short Inner
        legs.append({"symbol": short_ce_item["ce"]["symbol"], "action": "SELL", "option_type": "CE", "quantity": QUANTITY, "product": PRODUCT})
        legs.append({"symbol": short_pe_item["pe"]["symbol"], "action": "SELL", "option_type": "PE", "quantity": QUANTITY, "product": PRODUCT})

        return legs

    def _execute_entry(self, legs):
        self.logger.info(f"Placing Iron Condor Order: {len(legs)} legs")

        try:
            resp = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=UNDERLYING_EXCHANGE,
                expiry_date=self.expiry,
                legs=legs
            )

            if resp.get("status") == "success":
                self.logger.info(f"Order Success: {resp.get('order_id')}")
                self.limiter.record()

                # Fetch fill prices (simulated or real)
                # In live, we might need to query orderbook. Here assuming market order fills near LTP.
                # We need entry prices for the tracker.
                # We will fetch a fresh quote or use the last known LTP from chain (approx).
                # Ideally, we get fill price from order response if available.

                # For this implementation, we will fetch current LTPs immediately to register position.
                # Or wait for position book.
                # Simpler: Use the LTPs from the chain we just analyzed, or fetch fresh quotes.

                # We will re-use the chain LTPs passed into find_legs? No, we don't have them here.
                # We will fetch fresh quotes for accuracy.
                entry_prices = []
                for leg in legs:
                    q = self.client.get_quote(leg["symbol"], OPTIONS_EXCHANGE)
                    price = safe_float(q.get("ltp")) if q else 0.0
                    entry_prices.append(price)

                self.tracker.add_legs(legs, entry_prices)
                self.last_entry_date = datetime.now().date()

            else:
                self.logger.error(f"Order Failed: {resp.get('message')}")

        except Exception as e:
            self.logger.error(f"Execution Error: {e}")

    def _close_position(self, reason):
        self.logger.info(f"Closing Position: {reason}")

        # Sort legs to BUY first (cover shorts) then SELL (close longs)
        # Shorts have action="SELL", we need to BUY. Longs have action="BUY", we need to SELL.
        # We need to execute opposite actions.

        close_legs = []
        for leg in self.tracker.open_legs:
            close_action = "BUY" if leg["action"].upper() == "SELL" else "SELL"
            close_legs.append({
                "symbol": leg["symbol"],
                "action": close_action,
                "option_type": leg.get("option_type", "CE"),
                "quantity": leg.get("quantity", 1),
                "product": PRODUCT
            })

        # Sort: BUY actions first
        close_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            resp = self.client.optionsmultiorder(
                strategy=f"{STRATEGY_NAME}_EXIT",
                underlying=UNDERLYING,
                exchange=UNDERLYING_EXCHANGE,
                expiry_date=self.expiry,
                legs=close_legs
            )

            if resp.get("status") == "success":
                self.logger.info("Position Closed Successfully")
                self.tracker.clear()
            else:
                self.logger.error(f"Exit Failed: {resp.get('message')}")
                # Critical: If exit fails, we might be stuck. Retry logic would go here.
        except Exception as e:
            self.logger.error(f"Exit Exception: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # 1. Check Market Status
                if not is_market_open_local():
                    self.logger.info("Market Closed. Sleeping...")
                    time.sleep(300)
                    continue

                # 2. Ensure Expiry
                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No expiry resolved.")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Get Option Chain
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=STRIKE_COUNT)
                if not valid:
                    self.logger.warning(f"Invalid Chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # 4. Exit Management
                if self.tracker.open_legs:
                    # Check Friday Expiry Special Exit (14:00)
                    ist_now = self.get_ist_time()
                    current_time = ist_now.time()
                    expiry_cutoff = datetime.strptime("14:00", "%H:%M").time()

                    if self.is_friday_expiry() and current_time >= expiry_cutoff:
                        self.logger.info("Friday Expiry 14:00 Force Exit")
                        self._close_position("friday_expiry_cutoff")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    # Standard SL/TP/Time check
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # 5. Entry Logic
                # Calculate indicators
                atm_item = next((item for item in chain if item.get("ce", {}).get("label") == "ATM"), None)
                straddle_premium = 0
                if atm_item:
                    ce_ltp = safe_float(atm_item.get("ce", {}).get("ltp"))
                    pe_ltp = safe_float(atm_item.get("pe", {}).get("ltp"))
                    straddle_premium = ce_ltp + pe_ltp

                # Log Status
                self.logger.info(format_kv(
                    spot=f"{underlying_ltp:.0f}",
                    straddle=f"{straddle_premium:.0f}",
                    expiry=self.expiry,
                    pos="OPEN" if self.tracker.open_legs else "FLAT",
                    credit=f"{self.tracker.net_credit_collected:.0f}"
                ))

                # Entry conditions
                can_trade = self.can_trade()
                premium_ok = straddle_premium >= MIN_STRADDLE_PREMIUM
                not_in_pos = not self.tracker.open_legs

                # Check One Trade Per Day logic (via TradeLimiter, but strict enforcement can be here)
                # self.limiter handles frequency, but if we want STRICT 1 per day, we check dates.

                entry_condition = can_trade and premium_ok and not_in_pos

                if self.debouncer.edge("entry_signal", entry_condition):
                    legs = self.find_legs(chain)
                    if legs:
                        self._execute_entry(legs)
                    else:
                        self.logger.warning("Could not identify valid legs for Iron Condor")

            except Exception as e:
                self.logger.error(f"Loop Error: {e}", exc_info=True)
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = SensexWeeklyStrategy()
    strategy.run()
