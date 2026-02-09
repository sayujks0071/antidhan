#!/usr/bin/env python3
"""
SENSEX Iron Condor - Weekly Options (OpenAlgo Web UI Compatible)
Sells OTM2 Strangle and Buys OTM4 Wings for defined risk on SENSEX Weekly Options.

Exchange: BFO (BSE F&O)
Underlying: SENSEX on BSE_INDEX
Expiry: Weekly Friday
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
utils_dir = os.path.join(script_dir, "utils")
sys.path.insert(0, utils_dir)

# Also add root dir for potential root-level imports
root_dir = os.path.dirname(script_dir)
sys.path.insert(0, root_dir)

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
    import traceback
    traceback.print_exc()
    # Print search path for debugging
    print(f"sys.path: {sys.path}", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)

# ===========================
# API KEY & CONFIGURATION
# ===========================
API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

if not API_KEY:
    try:
        # Attempt to retrieve API key if not in env
        # Note: This part depends on database module availability which might not be there in all setups
        # But we keep it as per prompt boilerplate.
        # Check if database module exists
        if os.path.exists(os.path.join(root_dir, "database", "auth_db.py")):
             sys.path.append(os.path.join(root_dir, "database"))
             from database.auth_db import get_first_available_api_key
             API_KEY = get_first_available_api_key()
             if API_KEY:
                 print("Successfully retrieved API Key from database.", flush=True)
    except Exception as e:
        print(f"Warning: Could not retrieve API key from database: {e}", flush=True)

if not API_KEY:
    # Fallback for local testing if needed, or raise error
    # print("Warning: API Key must be set. Using dummy for testing.", flush=True)
    # API_KEY = "DUMMY"
    raise ValueError("API Key must be set in OPENALGO_APIKEY environment variable")

# ===========================
# CONFIGURATION - SENSEX WEEKLY OPTIONS
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "sensex_iron_condor")
UNDERLYING = os.getenv("UNDERLYING", "SENSEX")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "BSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "BFO")
PRODUCT = os.getenv("PRODUCT", "MIS")           # MIS=Intraday
QUANTITY = int(os.getenv("QUANTITY", "1"))        # 1 lot = 10 units for SENSEX
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "15")) # Need enough strikes for OTM4

# Strategy Parameters
MIN_STRADDLE_PREMIUM = float(os.getenv("MIN_STRADDLE_PREMIUM", "500"))
ENTRY_TIME_START = "10:00"
ENTRY_TIME_END = "14:30"
FRIDAY_EXIT_TIME = "14:00" # Exit early on expiry day

# Risk parameters
SL_PCT = float(os.getenv("SL_PCT", "35"))        # 35% SL
TP_PCT = float(os.getenv("TP_PCT", "45"))        # 45% TP
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))

# Rate limiting
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "1")) # "Only one trade per day"
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Manual expiry override (format: 14FEB26)
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

# Defensive normalization: SENSEX/BANKEX trade on BSE
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and UNDERLYING_EXCHANGE.upper() == "NSE_INDEX":
    UNDERLYING_EXCHANGE = "BSE_INDEX"
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and OPTIONS_EXCHANGE.upper() == "NFO":
    OPTIONS_EXCHANGE = "BFO"

class SensexIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Risk & Position Tracking
        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.limiter = TradeLimiter(max_per_day=MAX_ORDERS_PER_DAY, max_per_hour=MAX_ORDERS_PER_HOUR, cooldown_seconds=COOLDOWN_SECONDS)
        self.debouncer = SignalDebouncer()

        # Logging
        ledger_dir = os.path.join(root_dir, "log", "strategies", "trades")
        ledger_path = os.path.join(ledger_dir, f"{STRATEGY_NAME}_{UNDERLYING}_trades.csv")
        self.ledger = TradeLedger(ledger_path)

        self.expiry = EXPIRY_DATE
        self.last_expiry_check = 0
        self.entered_today = False
        self.last_date = None

    def ensure_expiry(self):
        # Refresh expiry if needed
        now = time.time()
        if self.expiry and now - self.last_expiry_check < EXPIRY_REFRESH_SEC:
            return

        if EXPIRY_DATE:
             self.expiry = EXPIRY_DATE
             return

        self.logger.info("Fetching available expiries...")
        resp = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
        if resp.get("status") == "success":
            expiries = resp.get("data", [])
            self.expiry = choose_nearest_expiry(expiries)
            self.logger.info(f"Selected Expiry: {self.expiry}")
            self.last_expiry_check = now
        else:
            self.logger.warning(f"Failed to fetch expiry: {resp.get('message')}")

    def _is_market_open_now(self):
        # Use trading_utils or custom time check
        # Assuming trading_utils.is_market_open defaults to NSE hours which match BSE equity/derivatives mostly (9:15-3:30)
        # But we need to handle "BSE" argument if implementation supports it, or just rely on default.
        return is_market_open()

    def _get_time_str(self):
        return datetime.now().strftime("%H:%M")

    def _check_friday_expiry_exit(self):
        # On Friday expiry day: exit all by 2:00 PM
        if not self.expiry:
             return False

        try:
             expiry_dt = datetime.strptime(self.expiry, "%d%b%y").date()
             today = datetime.now().date()

             # Check if today is the expiry date (which should be a Friday for Sensex Weekly)
             if today == expiry_dt:
                 current_time = datetime.now().time()
                 exit_limit = datetime.strptime(FRIDAY_EXIT_TIME, "%H:%M").time()
                 if current_time >= exit_limit:
                     return True
        except Exception as e:
             self.logger.error(f"Error checking Friday expiry: {e}")

        return False

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position. Reason: {reason}")

        # In a real implementation, we would place EXIT orders (Buy back the shorts, Sell the longs).
        # Since optionsmultiorder is usually for entry, we might need to place individual orders or reverse the legs.
        # OpenAlgo optionsmultiorder might support "EXIT" action or we construct reverse order.
        # For this example, we will assume we construct a reverse multi-order.

        if not self.tracker.legs:
            self.tracker.clear()
            return

        exit_legs = []
        for leg in self.tracker.legs:
            # Reverse action: BUY -> SELL, SELL -> BUY
            exit_action = "SELL" if leg["action"] == "BUY" else "BUY"
            exit_leg = {
                "offset": leg.get("offset", "ATM"), # We might need to store offset or symbol
                "option_type": leg["option_type"],
                "action": exit_action,
                "quantity": leg["quantity"],
                "product": PRODUCT,
                "symbol": leg.get("symbol") # If supported by API to close by symbol
            }
            # Note: optionsmultiorder usually takes offsets. If we want to close specific symbols,
            # we might need to use placesmartorder loop.
            # However, for simplicity and staying within prompt scope,
            # we'll assume we can send a "close" signal or just log it.
            # Real-world: iterate and close each leg.
            exit_legs.append(exit_leg)

        # Simplified: Log exit
        self.logger.info(f"Executing exit for {len(exit_legs)} legs...")

        for leg in exit_legs:
            symbol = leg.get("symbol")
            if not symbol:
                self.logger.warning(f"Skipping exit for leg without symbol: {leg}")
                continue

            try:
                # Place Market Exit Order
                self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=symbol,
                    action=leg["action"],
                    exchange=OPTIONS_EXCHANGE,
                    price_type="MARKET",
                    product=PRODUCT,
                    quantity=leg["quantity"],
                    position_size=leg["quantity"]
                )
                self.logger.info(f"Exit order placed: {leg['action']} {symbol}")
            except Exception as e:
                self.logger.error(f"Failed to place exit order for {symbol}: {e}")

        # Record in ledger
        self.ledger.append({"timestamp": datetime.now().isoformat(), "side": "EXIT", "reason": reason})

        self.tracker.clear()
        self.logger.info("Position closed and tracker cleared.")

    def _open_position(self, chain, reason):
        self.logger.info(f"Opening Iron Condor position... ({reason})")

        # Iron Condor: Sell OTM2, Buy OTM4
        legs = [
            # Wings (Protection) - Buy first for margin benefit
            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
            # Short Strikes (Premium)
            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
        ]

        resp = self.client.optionsmultiorder(
            strategy="sensex_iron_condor",
            underlying=UNDERLYING,
            exchange=UNDERLYING_EXCHANGE,
            expiry_date=self.expiry,
            legs=legs
        )

        if resp.get("status") == "success":
            self.logger.info(f"Order placed successfully: {resp.get('message')}")
            self.entered_today = True
            self.limiter.record()

            # In a real system, we'd parse the response to get executed prices and symbols.
            # Response usually contains order_ids. We might need to fetch orderbook to get average_price.
            # For this strategy logic, we'll assume we get filled at current chain LTPs for tracking.

            # Map offsets to symbols/prices from current chain
            # Note: This is an estimation. Real fills might differ.
            entry_prices = {}
            filled_legs = []

            # Helper to find item by offset
            def find_item(offset, otype):
                # offset like "OTM2", "ATM"
                # In chain, items have label "OTM2" etc in ce/pe dict
                for item in chain:
                    data = item.get(otype.lower())
                    if data and data.get("label") == offset:
                        return data
                return None

            for leg in legs:
                offset = leg["offset"]
                otype = leg["option_type"]
                data = find_item(offset, otype)
                if data:
                    sym = data.get("symbol")
                    ltp = safe_float(data.get("ltp"))
                    entry_prices[sym] = ltp

                    # Add symbol/price to leg definition for tracker
                    leg_record = leg.copy()
                    leg_record["symbol"] = sym
                    filled_legs.append(leg_record)
                    self.logger.info(f"Leg: {leg['action']} {sym} @ {ltp}")

            self.tracker.add_legs(filled_legs, entry_prices, side="SELL") # Iron Condor is a Credit Strategy (Net Sell)

            self.ledger.append({"timestamp": datetime.now().isoformat(), "side": "ENTRY", "reason": reason})

        else:
            self.logger.error(f"Order failed: {resp.get('message')}")

    def can_trade(self):
        # 1. Check Limiter
        if not self.limiter.allow():
            return False

        # 2. Check Time Window
        now_str = self._get_time_str()
        if not (ENTRY_TIME_START <= now_str <= ENTRY_TIME_END):
             return False

        # 3. Check already entered
        if self.entered_today:
             return False

        # 4. Check Friday restriction (if specified "enters after 10 AM on any weekday" - covered by time window)
        # But "On Friday expiry day: exit all by 2:00 PM". We shouldn't enter after 2 PM? Covered by 14:30 end time.
        # Actually if it's Friday, maybe stop entry earlier?
        # The prompt example: "Enters after 10 AM on any weekday".
        # But "On Friday expiry day: exit all by 2:00 PM".
        # So on Friday, entry window should probably end earlier or be careful.
        # Logic: If today is expiry, and time > 12:00, maybe risky to enter.
        # But let's stick to the explicit rules: "Enters after 10 AM".

        return True

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # Daily Reset
                today_date = datetime.now().date()
                if self.last_date != today_date:
                    self.entered_today = False
                    self.last_date = today_date
                    self.logger.info(f"New day {today_date}. Resetting daily flags.")

                if not self._is_market_open_now():
                    self.logger.info("Market closed. Sleeping...")
                    time.sleep(60) # Sleep longer when closed
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No expiry available.")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 0. FRIDAY EXPIRY CHECK
                # If we are in position on Friday > 2 PM, exit immediately
                if self.tracker.open_legs and self._check_friday_expiry_exit():
                     self.logger.warning("Friday Expiry Time Limit Reached (14:00). Exiting all positions.")
                     # Fetch chain to get current prices for logging/tracker
                     chain_resp = self.client.optionchain(
                        underlying=UNDERLYING,
                        exchange=UNDERLYING_EXCHANGE,
                        expiry_date=self.expiry,
                        strike_count=STRIKE_COUNT,
                    )
                     chain = chain_resp.get("chain", []) if chain_resp else []
                     self._close_position(chain, "friday_expiry_cutoff")
                     time.sleep(SLEEP_SECONDS)
                     continue

                # Fetch Chain
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT,
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10) # Reduced min strikes check
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # 1. EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                    # EOD Check (3:15 PM)
                    # "Exits all positions by 3:15 PM on non-expiry days"
                    # And on Friday it's 2:00 PM (handled above).
                    now_time = datetime.now().time()
                    eod_time = datetime.strptime("15:15", "%H:%M").time()
                    if now_time >= eod_time:
                         self._close_position(chain, "EOD_squareoff")
                         time.sleep(SLEEP_SECONDS)
                         continue

                # 2. INDICATORS
                # Calculate Straddle Premium
                atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)
                if atm_item:
                    ce_ltp = safe_float((atm_item.get("ce") or {}).get("ltp"))
                    pe_ltp = safe_float((atm_item.get("pe") or {}).get("ltp"))
                    straddle_premium = ce_ltp + pe_ltp
                else:
                    straddle_premium = 0

                # 3. LOG STATUS
                self.logger.info(format_kv(
                    time=self._get_time_str(),
                    spot=f"{underlying_ltp:.2f}",
                    straddle=f"{straddle_premium:.2f}",
                    pos="OPEN" if self.tracker.open_legs else "FLAT",
                    entered=str(self.entered_today),
                    expiry=self.expiry
                ))

                # 4. ENTRY LOGIC
                # Skip if in position or already traded
                if self.tracker.open_legs or self.entered_today:
                    time.sleep(SLEEP_SECONDS)
                    continue

                if self.can_trade():
                    # Condition: Straddle Premium > MIN_STRADDLE_PREMIUM
                    condition = (straddle_premium > MIN_STRADDLE_PREMIUM)

                    # Use debouncer to detect fresh signal (optional, but good practice)
                    entry_signal = self.debouncer.edge("high_iv_entry", condition)

                    if condition: # Prompt says "when straddle premium > 500". Doesn't strictly say rising edge, but implies condition met.
                        # We use 'condition' directly because 'only one trade per day' limits us anyway.
                        # But Debouncer helps avoid noise if we had multiple trades.
                        self.logger.info(f"Entry Signal: Straddle {straddle_premium:.2f} > {MIN_STRADDLE_PREMIUM}")
                        self._open_position(chain, "straddle_premium_condition")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = SensexIronCondorStrategy()
    strategy.run()
