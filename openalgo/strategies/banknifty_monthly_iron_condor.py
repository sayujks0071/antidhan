#!/usr/bin/env python3
"""
Bank Nifty Monthly Iron Condor - BANKNIFTY Options (OpenAlgo Web UI Compatible)
Sells OTM5 (~500 pts) strangles and buys OTM7 (~700 pts) wings for defined-risk theta decay.
Designed for Monthly Expiry contracts.

Strategy Profile: Conservative Monthly Income
- Sell OTM5 (Strike Gap 500)
- Buy OTM7 (Wing Width 200)
- Lot Size: 15 (Bank Nifty Standard)
- SL: 30% of Net Premium Collected
- TP: 50% of Net Premium Collected
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
openalgo_dir = os.path.dirname(script_dir) # openalgo/
utils_dir = os.path.join(script_dir, "utils") # openalgo/strategies/utils/

sys.path.insert(0, utils_dir)
sys.path.insert(0, openalgo_dir)

try:
    from datetime import timezone, timedelta
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_monthly_expiry,
        is_chain_valid,
        safe_float,
        safe_int,
        get_atm_strike,
        calculate_straddle_premium,
    )
    from strategy_common import SignalDebouncer, TradeLimiter, format_kv
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)

def is_market_open():
    """
    Checks if NSE market is open (09:15 - 15:30 IST).
    Uses UTC time + 5.5 hours to avoid pytz dependency.
    """
    # Current UTC time
    now_utc = datetime.now(timezone.utc)
    # Convert to IST (UTC + 5:30)
    ist_offset = timedelta(hours=5, minutes=30)
    now_ist = now_utc + ist_offset

    # Check weekend (0=Mon, 6=Sun)
    if now_ist.weekday() >= 5:
        return False

    current_time = now_ist.time()
    market_start = datetime.strptime("09:15", "%H:%M").time()
    market_end = datetime.strptime("15:30", "%H:%M").time()

    return market_start <= current_time <= market_end


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# Configuration Section
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "BankNiftyMonthlyIC")
UNDERLYING = os.getenv("UNDERLYING", "BANKNIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NSE")
PRODUCT = os.getenv("PRODUCT", "MIS")
# Bank Nifty Lot Size is typically 15 (as of late 2024/2025)
QUANTITY = safe_int(os.getenv("QUANTITY", "15"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "20")) # Enough to reach OTM7 (700 pts with 100 step)

# Strategy specific parameters
STRIKE_GAP = safe_int(os.getenv("STRIKE_GAP", "500"))
WING_WIDTH = safe_int(os.getenv("WING_WIDTH", "200"))

# SL/TP based on Net Credit Premium
SL_PCT = safe_float(os.getenv("SL_PCT", "30.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Time Filters
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "10:00")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")
# Guide: "ATM Threshold: If (ATM_CE + ATM_PE) < 900, IV is low... > 1500 IV is high"
# We want decent premium to sell.
MIN_PREMIUM = safe_float(os.getenv("MIN_PREMIUM", "900.0"))


API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

# root_dir points to repo root (grandparent of script_dir)
root_dir = os.path.dirname(os.path.dirname(script_dir))
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


class BankNiftyMonthlyICStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        # Replaced APIClient with OptionChainClient (which now has placesmartorder)

        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_check = 0

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")
        self.logger.info(format_kv(
            underlying=UNDERLYING,
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold=MAX_HOLD_MIN,
            max_orders=MAX_ORDERS_PER_DAY,
            lot_size=QUANTITY
        ))

    def ensure_expiry(self):
        """Refreshes expiry date if needed."""
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > EXPIRY_REFRESH_SEC):
            try:
                res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
                if res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        # Use Monthly Expiry Logic (Last Thursday usually)
                        self.expiry = choose_monthly_expiry(dates)
                        self.last_expiry_check = now
                        self.logger.info(f"Selected Monthly Expiry: {self.expiry}")
                    else:
                        self.logger.warning("No expiry dates found.")
                else:
                    self.logger.warning(f"Expiry fetch failed: {res.get('message')}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def is_time_window_open(self):
        """Checks if current time is within entry window."""
        now = datetime.now().time()
        try:
            start = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
            end = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()
            return start <= now <= end
        except ValueError:
            self.logger.error("Invalid time format in configuration")
            return False

    def should_terminate(self):
        """Checks if strategy should terminate for the day (after 3:15 PM)."""
        now = datetime.now().time()
        try:
            exit_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
            return now >= exit_time
        except ValueError:
            return False

    def get_leg_details_by_strike(self, chain, strike, option_type):
        """Helper to resolve symbol and LTP from chain based on strike price."""
        for item in chain:
            if item.get("strike") == strike:
                opt = item.get(option_type.lower(), {})
                if opt.get("symbol"):
                    return {
                        "symbol": opt.get("symbol"),
                        "ltp": safe_float(opt.get("ltp", 0)),
                        "quantity": QUANTITY,
                        "product": PRODUCT
                    }
        return None

    def _close_position(self, chain, reason):
        """Closes all open positions with prioritized ordering."""
        self.logger.info(f"Closing position. Reason: {reason}")

        exit_legs = []
        for leg in self.tracker.open_legs:
            # Reverse action: If we SOLD to open, we BUY to close.
            action = "BUY" if leg.get("action") == "SELL" else "SELL"
            exit_legs.append({
                "symbol": leg["symbol"],
                "action": action,
                "quantity": leg["quantity"],
                "product": PRODUCT,
                "pricetype": "MARKET"
            })

        if not exit_legs:
            self.logger.warning("No open legs to close, but close requested.")
            self.tracker.clear()
            return

        # CRITICAL: Sort legs to prioritize BUY orders (Covering Shorts) first.
        # This prevents margin spikes or rejection when closing complex positions.
        # BUY (Close Short) = Priority 0
        # SELL (Close Long) = Priority 1
        exit_legs.sort(key=lambda x: 0 if x['action'] == 'BUY' else 1)

        for leg in exit_legs:
            try:
                # Use self.client (OptionChainClient) which now has placesmartorder
                res = self.client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=leg["symbol"],
                    action=leg["action"],
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=leg["product"],
                    quantity=leg["quantity"],
                    position_size=leg["quantity"]
                )
                self.logger.info(f"Exit Order: {leg['symbol']} {leg['action']} -> {res}")
                time.sleep(0.5) # Slight delay to ensure sequential execution
            except Exception as e:
                self.logger.error(f"Exit failed for {leg['symbol']}: {e}")

        self.tracker.clear()
        self.logger.info("Position closed and tracker cleared.")

    def check_exit_conditions_local(self, chain):
        """
        Calculates PnL based on Net Credit to strictly follow strategy intent.
        Returns: (bool exit_now, string reason)
        """
        if not self.tracker.open_legs:
            return False, ""

        # 1. Time Stop
        if self.tracker.entry_time:
            minutes_held = (datetime.now() - self.tracker.entry_time).total_seconds() / 60
            if minutes_held >= MAX_HOLD_MIN:
                return True, "time_stop"

        # 2. PnL Check (Net Credit Basis)
        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        net_credit_collected = 0.0
        current_cost_to_close = 0.0

        for leg in self.tracker.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            curr = ltp_map.get(sym, entry)
            qty = leg.get("quantity", 1)

            if leg["action"].upper() == "SELL":
                # We collected premium
                net_credit_collected += (entry * qty)
                # To close, we buy back at current
                current_cost_to_close += (curr * qty)
            else: # BUY
                # We paid premium
                net_credit_collected -= (entry * qty)
                # To close, we sell at current (credit)
                current_cost_to_close -= (curr * qty)

        # PnL = Net Credit Collected - Cost to Close
        # Example: Collected 100. Cost to close 80. PnL = 20.
        # Example: Collected 100. Cost to close 150. PnL = -50.
        pnl = net_credit_collected - current_cost_to_close

        # Percentage of MAX PROFIT (Net Credit)
        if net_credit_collected == 0:
            return False, ""

        pnl_pct = (pnl / abs(net_credit_collected)) * 100

        # Check Stops
        if pnl_pct <= -SL_PCT:
            return True, f"stop_loss_hit ({pnl_pct:.1f}%)"

        if pnl_pct >= TP_PCT:
            return True, f"take_profit_hit ({pnl_pct:.1f}%)"

        return False, ""

    def run(self):
        self.logger.info("Starting BankNifty Monthly IC Strategy Loop...")

        while True:
            try:
                # 1. Check Market Open
                if not is_market_open():
                    self.logger.debug("Market is closed. Sleeping...")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 2. Ensure Expiry
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Get Option Chain
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=14) # Need enough depth for OTM7
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])

                # 4. EXIT MANAGEMENT
                if self.tracker.open_legs:
                    # Use Local Logic for precise Net Credit PnL
                    exit_now, exit_reason = self.check_exit_conditions_local(chain)
                    if exit_now or self.should_terminate():
                        reason = exit_reason if exit_now else "EOD Auto-Squareoff"
                        self._close_position(chain, reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # 5. ENTRY LOGIC
                if not self.tracker.open_legs and self.is_time_window_open():

                    if not self.limiter.allow():
                        self.logger.debug("Trade limiter active. Skipping entry.")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    atm_strike = get_atm_strike(chain)
                    if not atm_strike:
                        self.logger.warning("ATM strike not found.")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    premium = calculate_straddle_premium(chain, atm_strike)
                    self.logger.info(format_kv(spot="ATM", strike=atm_strike, premium=premium))

                    is_entry_signal = (premium >= MIN_PREMIUM)

                    if self.debouncer.edge("ENTRY_SIGNAL", is_entry_signal):
                        self.logger.info("Entry signal detected. Placing Monthly Iron Condor orders...")

                        # Iron Condor Definition (Monthly):
                        # Strike Gap: 500 (OTM5)
                        # Wing Width: 200 (OTM7 = 500+200)

                        sell_ce_strike = atm_strike + STRIKE_GAP
                        buy_ce_strike = atm_strike + STRIKE_GAP + WING_WIDTH
                        sell_pe_strike = atm_strike - STRIKE_GAP
                        buy_pe_strike = atm_strike - STRIKE_GAP - WING_WIDTH

                        # Define legs: (strike, type, action)
                        # Order matters: Buy wings first for margin benefit (though optionsmultiorder usually handles this,
                        # we define intended structure here)
                        definitions = [
                            (buy_ce_strike, "CE", "BUY"),
                            (buy_pe_strike, "PE", "BUY"),
                            (sell_ce_strike, "CE", "SELL"),
                            (sell_pe_strike, "PE", "SELL")
                        ]

                        tracking_legs = []
                        entry_prices = []
                        valid_setup = True

                        # Resolve symbols first
                        for strike, otype, action in definitions:
                            details = self.get_leg_details_by_strike(chain, strike, otype)
                            if details:
                                details["action"] = action
                                details["option_type"] = otype
                                tracking_legs.append(details)
                                entry_prices.append(details["ltp"])
                            else:
                                self.logger.warning(f"Could not resolve leg: Strike {strike} {otype}")
                                valid_setup = False
                                break

                        if valid_setup:
                            # Construct API payload
                            api_legs = []
                            for leg in tracking_legs:
                                api_legs.append({
                                    "symbol": leg["symbol"],
                                    "option_type": leg["option_type"],
                                    "action": leg["action"],
                                    "quantity": QUANTITY,
                                    "product": PRODUCT
                                })

                            try:
                                response = self.client.optionsmultiorder(
                                    strategy=STRATEGY_NAME,
                                    underlying=UNDERLYING,
                                    exchange=UNDERLYING_EXCHANGE,
                                    expiry_date=self.expiry,
                                    legs=api_legs
                                )

                                if response.get("status") == "success":
                                    self.logger.info(f"Order Success: {response}")
                                    self.limiter.record()

                                    # Add to tracker with correct signature: legs, entry_prices, side
                                    self.tracker.add_legs(
                                        legs=tracking_legs,
                                        entry_prices=entry_prices,
                                        side="SELL" # Net credit strategy
                                    )
                                    self.logger.info("Iron Condor positions tracked.")
                                else:
                                    self.logger.error(f"Order Failed: {response.get('message')}")

                            except Exception as e:
                                self.logger.error(f"Order Execution Error: {e}")
                        else:
                            self.logger.warning("Setup invalid (missing strikes). Skipping.")

                    else:
                        if not is_entry_signal:
                            self.logger.debug(f"Premium {premium} < {MIN_PREMIUM}. Waiting.")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    try:
        strategy = BankNiftyMonthlyICStrategy()
        strategy.run()
    except KeyboardInterrupt:
        print("Strategy stopped by user.")
    except Exception as e:
        print(f"Critical Error: {e}")
        sys.exit(1)
