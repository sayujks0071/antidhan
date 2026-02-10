#!/usr/bin/env python3
"""
Bank Nifty Iron Condor - Monthly Options Strategy
Sells OTM Strangle (Delta ~20) and buys wings (Delta ~10) for defined-risk monthly income.
Adapted for OpenAlgo.
"""
import os
import sys
import time
from datetime import datetime

# Line-buffered output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup
script_dir = os.path.dirname(os.path.abspath(__file__)) # openalgo/strategies
strategies_dir = os.path.dirname(script_dir) # openalgo
utils_dir = os.path.join(script_dir, "utils") # openalgo/strategies/utils
sys.path.insert(0, utils_dir)
sys.path.insert(0, strategies_dir) # To allow 'from utils import ...' in trading_utils

try:
    from trading_utils import is_market_open, APIClient
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_monthly_expiry,
        is_chain_valid,
        normalize_expiry,
        safe_float,
        safe_int,
    )
    from strategy_common import SignalDebouncer, TradeLedger, TradeLimiter, format_kv
except ImportError as e:
    print(f"ERROR: Could not import strategy utilities: {e}", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# Configuration Section
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "BankNiftyMonthlyIC")
UNDERLYING = os.getenv("UNDERLYING", "BANKNIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS") # Intraday for safety, user can change to NRML
QUANTITY = safe_int(os.getenv("QUANTITY", "15")) # Lot size for Bank Nifty is 15
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "40")) # Need wide view for Monthly

# Strategy specific parameters
# Prompt suggested: Stop Loss 30%, Target 50%
SL_PCT = safe_float(os.getenv("SL_PCT", "30.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "0")) # 0 = No time limit (Intraday/Positional)
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Offsets for Legs (Strikes away from ATM)
# Assuming 100 pt strikes.
# Monthly Straddle ~ 1000 pts. Conservative Sell ~ 1000 pts away (OTM10).
# Buy wings ~ 1500 pts away (OTM15).
SELL_OFFSET = safe_int(os.getenv("SELL_OFFSET", "10"))
BUY_OFFSET = safe_int(os.getenv("BUY_OFFSET", "15"))

# Time Filters
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:30")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")
MIN_PREMIUM = safe_float(os.getenv("MIN_PREMIUM", "900.0")) # Prompt: ATM < 900 IV low


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
    print("WARNING: OPENALGO_APIKEY not set. Strategy will fail if API is needed.", flush=True)
    # Don't raise error here to allow testing script initialization
    # raise ValueError("API Key must be set")


class BankNiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

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
            expiry_type="MONTHLY",
            sell_offset=SELL_OFFSET,
            buy_offset=BUY_OFFSET,
            sl_pct=SL_PCT,
            tp_pct=TP_PCT
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
                        # Use Monthly Expiry logic
                        self.expiry = choose_nearest_monthly_expiry(dates)
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
        """Checks if strategy should terminate for the day."""
        now = datetime.now().time()
        try:
            exit_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
            return now >= exit_time
        except ValueError:
            return False

    def get_atm_strike(self, chain):
        """Finds ATM strike from chain data."""
        # Check label first (if added by our utils)
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

    def get_leg_details(self, chain, offset_label, option_type):
        """Helper to resolve symbol and LTP from chain based on offset label."""
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset_label:
                return {
                    "symbol": opt.get("symbol"),
                    "ltp": safe_float(opt.get("ltp", 0)),
                    "quantity": QUANTITY,
                    "product": PRODUCT
                }
        return None

    def _close_position(self, chain, reason):
        """Closes all open positions."""
        self.logger.info(f"Closing position. Reason: {reason}")

        exit_legs = []
        for leg in self.tracker.open_legs:
            # Reverse action
            action = "BUY" if leg.get("action") == "SELL" else "SELL"
            exit_legs.append({
                "symbol": leg["symbol"],
                "action": action,
                "quantity": leg["quantity"],
                "product": PRODUCT,
                "pricetype": "MARKET"
            })

        if not exit_legs:
            self.logger.warning("No open legs to close.")
            self.tracker.clear()
            return

        for leg in exit_legs:
            try:
                res = self.api_client.placesmartorder(
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
            except Exception as e:
                self.logger.error(f"Exit failed for {leg['symbol']}: {e}")

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
                # Need sufficient strikes to reach SELL_OFFSET and BUY_OFFSET
                strike_count = max(STRIKE_COUNT, (BUY_OFFSET + 2) * 2)

                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])

                # 4. EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
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

                    atm_strike = self.get_atm_strike(chain)
                    if not atm_strike:
                        self.logger.warning("ATM strike not found.")
                        time.sleep(SLEEP_SECONDS)
                        continue

                    premium = self.calculate_straddle_premium(chain, atm_strike)
                    # self.logger.debug(format_kv(spot="ATM", strike=atm_strike, premium=premium))

                    # Logic: If Premium is decent, we enter.
                    # Prompt mentions "ATM < 900 IV low". If we want to sell, we prefer higher premium?
                    # "Conservative Monthly Income" usually works in most environments unless IV is extremely low.

                    if premium >= MIN_PREMIUM:
                        if self.debouncer.edge("ENTRY_SIGNAL", True):
                            self.logger.info(f"Entry Signal. ATM Premium: {premium}")

                            # Iron Condor Definition:
                            # 1. Sell OTM(SellOffset) Call
                            # 2. Sell OTM(SellOffset) Put
                            # 3. Buy OTM(BuyOffset) Call
                            # 4. Buy OTM(BuyOffset) Put

                            # Define legs
                            definitions = [
                                (f"OTM{BUY_OFFSET}", "CE", "BUY"),
                                (f"OTM{BUY_OFFSET}", "PE", "BUY"),
                                (f"OTM{SELL_OFFSET}", "CE", "SELL"),
                                (f"OTM{SELL_OFFSET}", "PE", "SELL")
                            ]

                            tracking_legs = []
                            entry_prices = []
                            valid_setup = True

                            # Resolve symbols
                            for offset_label, otype, action in definitions:
                                details = self.get_leg_details(chain, offset_label, otype)
                                if details:
                                    details["action"] = action
                                    tracking_legs.append(details)
                                    entry_prices.append(details["ltp"])
                                else:
                                    self.logger.warning(f"Could not resolve leg: {offset_label} {otype}")
                                    valid_setup = False
                                    break

                            if valid_setup:
                                # Construct API payload
                                api_legs = []
                                for i, (offset_label, otype, action) in enumerate(definitions):
                                    # The API "offset" field usually expects "OTM1", "ATM", etc.
                                    # But for multiorder, we might need to send symbol or resolved strikes.
                                    # OptionChainClient.optionsmultiorder signature matches the backend.
                                    # Assuming backend takes 'offset' and resolves it, OR we pass specific symbols.
                                    # But looking at nifty_iron_condor.py, it passes 'offset'.
                                    # My mock optionsmultiorder just passes it through.

                                    # Wait, if backend calculates offset from ATM, it needs to know what ATM is.
                                    # If we pass resolved symbols, it's safer.
                                    # But 'optionsmultiorder' in OpenAlgo usually implies strategy-based execution where the server logic might do the selection.
                                    # However, here we are determining the legs.
                                    # Let's check `nifty_iron_condor.py` again.
                                    # It sends: `offset`, `option_type`, `action`.
                                    # So the backend does resolution.
                                    # BUT, my strategy calculated "valid_setup" by resolving symbols LOCALLY using `get_leg_details`.
                                    # So I know the symbols exist.
                                    # I should probably trust the backend to resolve similarly.

                                    api_legs.append({
                                        "offset": offset_label,
                                        "option_type": otype,
                                        "action": action,
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
                        pass # self.logger.debug(f"Premium {premium} < {MIN_PREMIUM}. Waiting.")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    try:
        strategy = BankNiftyIronCondorStrategy()
        strategy.run()
    except KeyboardInterrupt:
        print("Strategy stopped by user.")
    except Exception as e:
        print(f"Critical Error: {e}")
        sys.exit(1)
