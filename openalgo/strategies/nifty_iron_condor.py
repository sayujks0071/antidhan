#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120. Sells OTM2, Buys OTM4. Max hold 45 mins. 1 trade/day.
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


# Configuration Section
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Strategy specific parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "40.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Time Filters
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "10:00")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30") # Don't enter too late
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")
MIN_PREMIUM = safe_float(os.getenv("MIN_PREMIUM", "120.0")) # Minimum straddle premium to sell


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


class IronCondorTracker(OptionPositionTracker):
    """
    Custom tracker for Iron Condor that calculates SL/TP based on Short Leg Premium.
    """
    def should_exit(self, chain):
        """
        Checks exit conditions based on current chain data.
        Returns: (bool exit_now, list legs, string reason)
        """
        if not self.open_legs:
            return False, [], ""

        # 1. Time Stop
        if self.entry_time:
            minutes_held = (datetime.now() - self.entry_time).total_seconds() / 60
            if minutes_held >= self.max_hold_min:
                return True, self.open_legs, f"time_stop ({int(minutes_held)}m)"

        # 2. PnL Check
        # Create a lookup map: symbol -> ltp
        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        total_pnl = 0.0
        short_premium_basis = 0.0

        for leg in self.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            curr = ltp_map.get(sym, entry) # Fallback to entry if no LTP found (neutral)
            action = leg["action"].upper()

            if action == "SELL":
                # Short Leg PnL: Entry - Current
                leg_pnl = (entry - curr)
                short_premium_basis += entry
            else:
                # Long Leg PnL: Current - Entry
                leg_pnl = (curr - entry)

            total_pnl += leg_pnl

        # If short_premium_basis is 0 (shouldn't happen for Iron Condor), avoid div by zero
        if short_premium_basis == 0:
            return False, [], ""

        pnl_pct = (total_pnl / short_premium_basis) * 100

        # Check Stops
        # SL: pnl_pct <= -SL_PCT (Loss)
        if pnl_pct <= -self.sl_pct:
            return True, self.open_legs, f"stop_loss_hit ({pnl_pct:.1f}%)"

        # TP: pnl_pct >= TP_PCT (Profit)
        if pnl_pct >= self.tp_pct:
            return True, self.open_legs, f"take_profit_hit ({pnl_pct:.1f}%)"

        return False, [], ""


class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Use custom tracker
        self.tracker = IronCondorTracker(
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
            min_premium=MIN_PREMIUM
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
                        self.expiry = choose_nearest_expiry(dates)
                        self.last_expiry_check = now
                        self.logger.info(f"Selected Expiry: {self.expiry}")
                    else:
                        self.logger.warning("No expiry dates found.")
                else:
                    self.logger.warning(f"Expiry fetch failed: {res.get('message')}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def is_entry_window_open(self):
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

    def get_atm_strike(self, chain):
        """Finds ATM strike from chain data."""
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return item["strike"]
        return None

    def calculate_straddle_premium(self, chain, atm_strike):
        """Calculates combined premium of ATM CE and PE."""
        ce_ltp = 0.0
        pe_ltp = 0.0

        for item in chain:
            if item["strike"] == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                break

        return ce_ltp + pe_ltp

    def get_leg_details(self, chain, offset, option_type):
        """Helper to resolve symbol and LTP from chain based on offset."""
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset:
                return {
                    "symbol": opt.get("symbol"),
                    "ltp": safe_float(opt.get("ltp", 0)),
                    "quantity": QUANTITY,
                    "product": PRODUCT
                }
        return None

    def _close_position(self, chain, reason):
        """Closes all open positions, prioritizing BUYs (closing shorts) then SELLs."""
        self.logger.info(f"Closing position. Reason: {reason}")

        exit_orders = []
        for leg in self.tracker.open_legs:
            # To close: If opened with SELL, we BUY. If opened with BUY, we SELL.
            close_action = "BUY" if leg.get("action") == "SELL" else "SELL"

            exit_orders.append({
                "symbol": leg["symbol"],
                "action": close_action,
                "quantity": leg["quantity"],
                "product": PRODUCT,
                "pricetype": "MARKET"
            })

        if not exit_orders:
            self.logger.warning("No open legs to close, but close requested.")
            self.tracker.clear()
            return

        # Sort: BUYs first (to cover shorts), then SELLs
        exit_orders.sort(key=lambda x: 0 if x['action'] == 'BUY' else 1)

        for order in exit_orders:
            try:
                # Use placesmartorder for single leg execution
                res = self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=order["symbol"],
                    action=order["action"],
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=order["product"],
                    quantity=order["quantity"],
                    position_size=0 # Closing position, target size 0 (or just executing order)
                )
                self.logger.info(f"Exit Order: {order['symbol']} {order['action']} -> {res}")
            except Exception as e:
                self.logger.error(f"Exit failed for {order['symbol']}: {e}")

        self.tracker.clear()
        self.logger.info("Position closed and tracker cleared.")

    def run(self):
        self.logger.info("Starting Strategy Loop...")

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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])

                # 4. EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # Force exit if EOD or Stop hit
                    if exit_now or self.should_terminate():
                        reason = exit_reason if exit_now else "EOD Auto-Squareoff"
                        self._close_position(chain, reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # 5. ENTRY LOGIC
                if not self.tracker.open_legs and self.is_entry_window_open() and not self.should_terminate():

                    if not self.limiter.allow():
                        self.logger.debug("Trade limiter active or max trades reached. Skipping entry.")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    atm_strike = self.get_atm_strike(chain)
                    if not atm_strike:
                        self.logger.warning("ATM strike not found.")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    premium = self.calculate_straddle_premium(chain, atm_strike)
                    # Use debug for frequent checks, info for significant events
                    if int(time.time()) % 60 == 0:
                        self.logger.debug(format_kv(spot="ATM", strike=atm_strike, premium=premium))

                    if premium > MIN_PREMIUM:
                        if self.debouncer.edge("ENTRY_SIGNAL", True):
                            self.logger.info(f"Entry Signal! Premium {premium} > {MIN_PREMIUM}. Placing Orders...")

                            # Iron Condor Definition:
                            # Sell OTM2 Strangle (CE+PE)
                            # Buy OTM4 Wings (CE+PE)

                            definitions = [
                                ("OTM4", "CE", "BUY"),
                                ("OTM4", "PE", "BUY"),
                                ("OTM2", "CE", "SELL"),
                                ("OTM2", "PE", "SELL")
                            ]

                            tracking_legs = []
                            entry_prices = []
                            api_legs = []
                            valid_setup = True

                            for offset, otype, action in definitions:
                                details = self.get_leg_details(chain, offset, otype)
                                if details:
                                    details["action"] = action
                                    tracking_legs.append(details)
                                    entry_prices.append(details["ltp"])

                                    api_legs.append({
                                        "offset": offset,
                                        "option_type": otype,
                                        "action": action,
                                        "quantity": QUANTITY,
                                        "product": PRODUCT
                                    })
                                else:
                                    self.logger.warning(f"Could not resolve leg: {offset} {otype}")
                                    valid_setup = False
                                    break

                            if valid_setup:
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

                                        self.tracker.add_legs(
                                            legs=tracking_legs,
                                            entry_prices=entry_prices,
                                            side="SELL"
                                        )
                                        self.logger.info("Iron Condor positions tracked.")
                                    else:
                                        self.logger.error(f"Order Failed: {response.get('message')}")

                                except Exception as e:
                                    self.logger.error(f"Order Execution Error: {e}")
                            else:
                                self.logger.warning("Setup invalid (missing strikes). Skipping.")

                    else:
                        # Reset debouncer if premium drops?
                        # No, usually we just wait. If it goes back up, we might re-enter?
                        # But prompt says "When straddle premium is above 120".
                        # Debouncer prevents rapid firing.
                        pass

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    try:
        strategy = NiftyIronCondorStrategy()
        strategy.run()
    except KeyboardInterrupt:
        print("Strategy stopped by user.")
    except Exception as e:
        print(f"Critical Error: {e}")
        sys.exit(1)
