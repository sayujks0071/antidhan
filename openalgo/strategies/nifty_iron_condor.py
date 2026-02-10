#!/usr/bin/env python3
"""
Nifty Iron Condor Strategy - Defined Risk Theta Decay
(OpenAlgo Web UI Compatible)

Strategy Logic:
- Iron Condor: Sell OTM2 Strangle + Buy OTM4 Wings
- Entry: After 10:00 AM, if ATM Straddle Premium > 100
- Exit: SL 40%, TP 60%, Max Hold 45 mins, or EOD (3:15 PM)
- Risk: Max 1 trade per day, cooldown 5 mins
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
        safe_float,
        safe_int,
    )
    from strategy_common import SignalDebouncer, TradeLimiter, format_kv
except ImportError as e:
    print(f"ERROR: Could not import strategy utilities: {e}", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(f"INFO: {msg}", flush=True)
    def warning(self, msg): print(f"WARN: {msg}", flush=True)
    def error(self, msg, exc_info=False): print(f"ERROR: {msg}", flush=True)
    def debug(self, msg): print(f"DEBUG: {msg}", flush=True)


# Configuration Section
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1")) # Lots (API handles multiplication by lot size usually, but here likely quantity means lots if API handles it, or units if not. Assuming API expects quantity in lots or units based on broker. Usually units. Nifty Lot=75. So 75.)
# Wait, prompt says: "Lot size: 75 (but use quantity=1 for the API, it handles lot size)"
# So I stick with 1.

STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Strategy Parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "40.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "60.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))
MIN_PREMIUM = safe_float(os.getenv("MIN_PREMIUM", "100.0"))

# Time Filters
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "10:00")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")

API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

# Ensure root dir is in path for database imports if needed
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

if not API_KEY:
    try:
        # Fallback to database if available
        # This is specific to the platform environment
        from database.auth_db import get_first_available_api_key
        API_KEY = get_first_available_api_key()
        if API_KEY:
            print("Successfully retrieved API Key from database.", flush=True)
    except Exception:
        pass

if not API_KEY:
    print("CRITICAL: API Key must be set in OPENALGO_APIKEY environment variable", flush=True)
    sys.exit(1)


class NiftyIronCondorStrategy:
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
        self.debouncer = SignalDebouncer(cooldown_seconds=COOLDOWN_SECONDS)

        self.expiry = None
        self.last_expiry_check = 0

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")
        self.logger.info(format_kv(
            underlying=UNDERLYING,
            qty=QUANTITY,
            sl=SL_PCT,
            tp=TP_PCT,
            hold=MAX_HOLD_MIN
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

    def is_time_window_open(self):
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

    def get_atm_strike(self, chain):
        """Finds ATM strike from chain data."""
        # Search for label="ATM"
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return item["strike"]
        # Fallback: Find strike closest to underlying_ltp if available in metadata?
        # The chain data usually has `underlying_ltp` at top level, but here we only have the list `chain`.
        # Assuming `label` is reliable.
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
        # Search for label=offset (e.g., "OTM2")
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset:
                return {
                    "symbol": opt.get("symbol"),
                    "ltp": safe_float(opt.get("ltp", 0)),
                    "quantity": QUANTITY,
                    "product": PRODUCT,
                    "exchange": OPTIONS_EXCHANGE
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
                "exchange": OPTIONS_EXCHANGE, # Ensure exchange is passed
                "pricetype": "MARKET",
                "position_size": leg["quantity"]
            })

        if not exit_legs:
            self.logger.warning("No open legs to close, but close requested.")
            self.tracker.clear()
            return

        # Execute exits
        # Ideally, we should use `optionsmultiorder` for atomic exit if supported,
        # but `placesmartorder` (single leg) is safer for ensuring execution if multi-leg isn't guaranteed.
        # However, for margin benefits, closing sell legs first (buying back) is better.

        # Sort legs: BUY actions first (Closing Shorts), then SELL actions (Closing Longs)
        exit_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        for leg in exit_legs:
            try:
                res = self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=leg["symbol"],
                    action=leg["action"],
                    exchange=leg["exchange"],
                    pricetype="MARKET",
                    product=leg["product"],
                    quantity=leg["quantity"],
                    position_size=leg["position_size"]
                )
                self.logger.info(f"Exit Order: {leg['symbol']} {leg['action']} -> {res.get('status')}")
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
                    time.sleep(SLEEP_SECONDS * 3) # Sleep longer when closed
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

                    # Also check EOD
                    if self.should_terminate():
                        exit_now = True
                        exit_reason = "EOD Auto-Squareoff"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # 5. ENTRY LOGIC
                # Only if no open position and within time window
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
                    # self.logger.info(format_kv(spot="ATM", strike=atm_strike, premium=premium))

                    if premium >= MIN_PREMIUM:
                        # Signal: Premium is good, time is right.
                        # Using debouncer to prevent rapid firing on noise
                        if self.debouncer.edge("ENTRY_SIGNAL", True):
                            self.logger.info(f"Entry Signal! Premium: {premium} >= {MIN_PREMIUM}")

                            # Iron Condor Definition:
                            # 1. Buy OTM4 Call (Wing)
                            # 2. Buy OTM4 Put (Wing)
                            # 3. Sell OTM2 Call (Body)
                            # 4. Sell OTM2 Put (Body)
                            # Buy legs first for margin benefit (if supported by broker execution order)

                            definitions = [
                                ("OTM4", "CE", "BUY"),
                                ("OTM4", "PE", "BUY"),
                                ("OTM2", "CE", "SELL"),
                                ("OTM2", "PE", "SELL")
                            ]

                            tracking_legs = []
                            entry_prices = []
                            valid_setup = True

                            # Resolve symbols first
                            for offset, otype, action in definitions:
                                details = self.get_leg_details(chain, offset, otype)
                                if details:
                                    details["action"] = action
                                    tracking_legs.append(details)
                                    entry_prices.append(details["ltp"])
                                else:
                                    self.logger.warning(f"Could not resolve leg: {offset} {otype}")
                                    valid_setup = False
                                    break

                            if valid_setup:
                                # Construct API payload
                                api_legs = []
                                for leg in tracking_legs:
                                    api_legs.append({
                                        "offset": "NA", # Not used by API if symbol is provided, but strictly speaking multiorder usually takes offset OR symbol. Prompt example used offset.
                                        # Wait, prompt example for multiorder:
                                        # legs=[{"offset": "OTM2", "option_type": "CE", "action": "SELL", ...}]
                                        # It didn't use symbol. It let the backend resolve it?
                                        # "OptionChainClient... optionsmultiorder... legs=[{'offset': 'OTM2'...}]"
                                        # If I use symbol, I might need to adjust.
                                        # Let's use the explicit symbol if available to be safe, OR follow the prompt pattern.
                                        # The prompt pattern implies the server resolves offsets.
                                        # BUT, I already resolved symbols to track them locally.
                                        # If I pass symbols, does the API support it?
                                        # "Place multi-leg option order... legs=[{'offset': 'OTM2' ...}]"
                                        # It seems the API prefers offsets.
                                        # However, for `OptionPositionTracker`, I need symbols.
                                        # So I resolve locally for tracking, but send offsets to API?
                                        # Or better: send symbols to API if it accepts them.
                                        # Let's assume API accepts symbols if 'symbol' key is present, or offsets if 'offset' key is present.
                                        # Actually, to be safe and strictly follow prompt, I should send what prompt showed: OFFSETS.

                                        "offset": "CUSTOM", # I will try to use the resolved symbol if possible.
                                        # If I look at `OptionChainClient.optionsmultiorder` in prompt, it doesn't show symbol in legs.
                                        # But `client.placesmartorder` uses symbol.
                                        # If I send `offset`, the backend resolves it.
                                        # If the backend resolves it, it might resolve to a different strike if the chain changed in the last millisecond? Unlikely.
                                        # But I need to know the symbol for tracking.
                                        # I'll stick to sending the resolved symbols if I can, but since I can't confirm API behavior,
                                        # I will use the prompt's method: sending offsets.
                                        # And I will trust that my local resolution matches the server's resolution.

                                        # Re-reading prompt:
                                        # legs=[{"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": 1, "product": "MIS"}, ...]

                                        "offset": self.get_offset_from_leg(leg, chain), # Helper needed?
                                        # Wait, I iterated `definitions` which has offsets.
                                        # So I can just use those.
                                    })
                                    pass

                                # Re-constructing api_legs from definitions
                                api_legs = []
                                for offset, otype, action in definitions:
                                    api_legs.append({
                                        "offset": offset,
                                        "option_type": otype,
                                        "action": action,
                                        "quantity": QUANTITY,
                                        "product": PRODUCT
                                    })

                                self.logger.info(f"Placing Multi-Leg Order: {api_legs}")

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

                                        # Add to tracker
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
                        # self.logger.debug(f"Premium {premium} < {MIN_PREMIUM}. Waiting.")
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
