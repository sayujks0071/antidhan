#!/usr/bin/env python3
"""
Nifty Iron Condor Strategy (OpenAlgo Web UI Compatible)
Sell OTM2 Strangle + Buy OTM4 Wings. Entry > 10 AM, Straddle Premium > 120. Risk/Reward based on Net Credit.
"""
import os
import sys
import time
from datetime import datetime, timezone, timedelta, time as dt_time

# Line-buffered output (required for real-time log capture)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
# Correctly point to strategies/utils to find optionchain_utils.py
utils_dir = os.path.join(script_dir, "utils")
sys.path.insert(0, utils_dir)

# Define directories for potential root imports
strategies_dir = os.path.dirname(script_dir)

try:
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        normalize_expiry,
        safe_float,
        safe_int,
        get_atm_strike,
        calculate_straddle_premium,
    )
    from strategy_common import SignalDebouncer, TradeLedger, TradeLimiter, format_kv
except ImportError as e:
    print(f"ERROR: Could not import strategy utilities: {e}", flush=True)
    sys.exit(1)

# Robust import for trading_utils (handles missing httpx dependency)
try:
    from trading_utils import is_market_open, APIClient
except ImportError:
    print("Warning: trading_utils not found or httpx missing. Using local fallbacks.", flush=True)
    import requests

    def is_market_open(exchange="NSE"):
        """Local implementation of market open check."""
        ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

        # Weekend Check
        if ist_now.weekday() >= 5:  # 5=Sat, 6=Sun
            return False

        market_start = dt_time(9, 15)
        market_end = dt_time(15, 30)
        current_time = ist_now.time()

        return market_start <= current_time <= market_end

    class APIClient:
        """Local implementation of APIClient using requests."""
        def __init__(self, api_key, host="http://127.0.0.1:5000"):
            self.api_key = api_key
            self.host = host.rstrip('/')
            self.session = requests.Session()

        def placesmartorder(self, strategy, symbol, action, exchange, price_type, product, quantity, position_size):
            url = f"{self.host}/api/v1/placesmartorder"
            payload = {
                "apikey": self.api_key,
                "strategy": strategy,
                "symbol": symbol,
                "action": action,
                "exchange": exchange,
                "pricetype": price_type, # Note: Payload key is 'pricetype'
                "product": product,
                "quantity": str(quantity),
                "position_size": str(position_size),
                "price": "0",
                "trigger_price": "0",
                "disclosed_quantity": "0"
            }
            try:
                response = self.session.post(url, json=payload, timeout=10)
                return response.json()
            except Exception as e:
                return {"status": "error", "message": str(e)}


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
# SL/TP are percentages of NET CREDIT COLLECTED.
# Example: Collected 100 pts. SL 40% means stop if loss > 40 pts (PnL < -40).
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
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")
MIN_PREMIUM = safe_float(os.getenv("MIN_PREMIUM", "120.0"))

# API Key Retrieval
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
    Custom tracker for Iron Condor that calculates SL/TP based on NET CREDIT.
    Net Credit = (Sell Entry Premium) - (Buy Entry Premium)
    """
    def should_exit(self, chain):
        if not self.open_legs:
            return False, [], ""

        # 1. Time Stop
        if self.entry_time:
            minutes_held = (datetime.now() - self.entry_time).total_seconds() / 60
            if minutes_held >= self.max_hold_min:
                return True, self.open_legs, f"time_stop ({int(minutes_held)}m)"

        # 2. PnL Check based on Net Credit
        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        total_credit_collected = 0.0
        current_cost_to_close = 0.0

        for leg in self.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            curr = ltp_map.get(sym, entry)  # Fallback to entry if no LTP
            action = leg["action"].upper()

            # Using quantities? For simplicity assuming equal quantities (1 lot structure)
            # If quantity > 1, multiply by quantity.
            qty = safe_int(leg.get("quantity", 1))

            if action == "SELL":
                total_credit_collected += (entry * qty)
                current_cost_to_close += (curr * qty)
            else: # BUY
                total_credit_collected -= (entry * qty)
                current_cost_to_close -= (curr * qty)

        # Net Credit Strategy PnL: Credit Collected - Cost to Close
        pnl = total_credit_collected - current_cost_to_close

        if total_credit_collected == 0:
            return False, [], ""

        # PnL Percentage of MAX PROFIT (Net Credit)
        pnl_pct = (pnl / abs(total_credit_collected)) * 100

        # Check Stops
        if pnl_pct <= -self.sl_pct:
            return True, self.open_legs, f"stop_loss_hit ({pnl_pct:.1f}%)"

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
            return False

    def should_terminate(self):
        """Checks if strategy should terminate for the day (after 3:15 PM)."""
        now = datetime.now().time()
        try:
            exit_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
            return now >= exit_time
        except ValueError:
            return False

    def get_leg_details(self, chain, offset, option_type):
        """Resolves symbol and LTP from chain based on offset label."""
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
        # Action 'BUY' comes before 'SELL' alphabetically.
        exit_orders.sort(key=lambda x: 0 if x['action'] == 'BUY' else 1)

        for order in exit_orders:
            try:
                # Use price_type argument to match APIClient signature (standard or fallback)
                res = self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=order["symbol"],
                    action=order["action"],
                    exchange=OPTIONS_EXCHANGE,
                    price_type="MARKET",
                    product=order["product"],
                    quantity=order["quantity"],
                    position_size=0
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
                # 1. Market Hours Check
                if not is_market_open():
                    self.logger.debug("Market closed. Sleeping...")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 2. Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch Option Chain
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
                # Only if no open position and within time window
                if not self.tracker.open_legs and self.is_entry_window_open() and not self.should_terminate():

                    atm_strike = get_atm_strike(chain)
                    if not atm_strike:
                        self.logger.warning("ATM strike not found.")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    premium = calculate_straddle_premium(chain, atm_strike)
                    self.logger.info(format_kv(spot="ATM", strike=atm_strike, premium=premium))

                    # Signal Condition: Premium > Threshold
                    signal_active = (premium > MIN_PREMIUM)

                    # Debounce Signal (Rising Edge)
                    if self.debouncer.edge("ENTRY_SIGNAL", signal_active):

                        if not self.limiter.allow():
                            self.logger.info("Entry signal valid but trade limit reached.")
                        else:
                            self.logger.info(f"Entry Signal! Premium {premium} > {MIN_PREMIUM}. Placing Orders...")

                            # Iron Condor: Sell OTM2 Strangle, Buy OTM4 Wings
                            # Sell OTM2 CE/PE, Buy OTM4 CE/PE
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
                                            side="SELL" # Net Credit Strategy
                                        )
                                        self.logger.info("Iron Condor positions tracked.")
                                    else:
                                        self.logger.error(f"Order Failed: {response.get('message')}")

                                except Exception as e:
                                    self.logger.error(f"Order Execution Error: {e}")
                            else:
                                self.logger.warning("Setup invalid (missing strikes). Skipping.")

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
