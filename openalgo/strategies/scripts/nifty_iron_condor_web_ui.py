#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Sells OTM2 strangles and buys OTM4 protection, entering after 10 AM if straddle premium > 120.
"""
import os
import sys
import time
from datetime import datetime, time as dt_time

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

# API Key retrieval (MANDATORY)
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

class NiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Configuration Section
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyIronCondorWeb")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Management Parameters
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "20"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # Strategy Parameters
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Trackers and Utility Helpers
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        # State
        self.expiry = None
        self.last_expiry_check = 0
        self.entered_today = False
        self.reset_date = datetime.now().date()

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res["data"]
                    nearest = choose_nearest_expiry(dates)
                    if nearest:
                        self.expiry = nearest
                        self.last_expiry_check = now
                        self.logger.info(f"Set nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry: {e}")

    def can_trade(self):
        now = datetime.now()

        # Reset daily tracking
        if now.date() != self.reset_date:
            self.entered_today = False
            self.reset_date = now.date()

        current_time = now.time()

        # Time-based filters
        # Enters after 10 AM, recommend entry window before 2:30 PM (14:30)
        start_time = dt_time(10, 0)
        end_time = dt_time(14, 30)

        if not (start_time <= current_time <= end_time):
            return False

        # Daily entry limit flag
        if self.entered_today:
            return False

        # Trade limiter
        if not self.limiter.allow():
            return False

        return True

    def _close_position(self, chain, exit_reason):
        self.logger.info(f"event=trade action=CLOSE reason={exit_reason}")

        # Extract the exact option symbols from the open legs and close each individually using APIClient.placesmartorder
        for leg in self.tracker.open_legs:
            # Reversing the action to close
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            try:
                resp = self.client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg.get("quantity", self.quantity),
                    position_size=leg.get("quantity", self.quantity)
                )
                self.logger.info(f"Trade response for leg {leg['symbol']}: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} for {self.underlying}")

        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # EOD Square-off before 3:15 PM (15:15)
                current_time = datetime.now().time()
                if current_time >= dt_time(15, 15):
                    if self.tracker.open_legs:
                        # Find chain data just for LTP fallback, actually we can just close without fresh chain
                        chain_resp = self.client.optionchain(
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            strike_count=self.strike_count
                        )
                        chain = chain_resp.get("chain", []) if chain_resp else []
                        self._close_position(chain, "eod_squareoff")
                    time.sleep(self.sleep_seconds)
                    continue

                # Fetch Option Chain
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.warning(f"Invalid chain data: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")

                if not atm_strike:
                    # Fallback ATM strike lookup
                    for item in chain:
                        if item.get("ce", {}).get("label") == "ATM":
                            atm_strike = item["strike"]
                            break

                if not atm_strike:
                    time.sleep(self.sleep_seconds)
                    continue

                # EXIT MANAGEMENT FIRST (always check exits before entries)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS
                ce_ltp = 0.0
                pe_ltp = 0.0
                for item in chain:
                    if item["strike"] == atm_strike:
                        ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0.0))
                        pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0.0))
                        break

                straddle_premium = ce_ltp + pe_ltp

                spot_price = chain_resp.get("underlying_ltp", atm_strike)

                self.logger.info(format_kv(
                    spot=spot_price,
                    atm=atm_strike,
                    premium=straddle_premium,
                    time=current_time.strftime("%H:%M:%S")
                ))

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    # Enter after 10 AM when straddle premium is above 120
                    signal_condition = straddle_premium > self.min_straddle_premium

                    if self.debouncer.edge("iron_condor_entry", signal_condition):
                        self.logger.info(format_kv(
                            event="signal",
                            type="iron_condor_entry",
                            premium=straddle_premium,
                            min_required=self.min_straddle_premium
                        ))

                        # Prepare the multi-leg order
                        # BUY legs execute first, then SELL legs (for margin efficiency)
                        legs_req = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        self.logger.info(f"event=trade action=OPEN type=IRON_CONDOR")
                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=legs_req
                        )

                        self.logger.info(f"Trade response: {resp}")

                        # To add to tracker, we need to map the offsets to actual symbols and entry prices from the chain
                        # Map offsets to symbols and LTPs
                        otm2_ce = otm2_pe = otm4_ce = otm4_pe = None

                        for item in chain:
                            ce = item.get("ce", {})
                            pe = item.get("pe", {})

                            if ce.get("label") == "OTM2": otm2_ce = ce
                            if pe.get("label") == "OTM2": otm2_pe = pe
                            if ce.get("label") == "OTM4": otm4_ce = ce
                            if pe.get("label") == "OTM4": otm4_pe = pe

                        # If we have the required symbols, add to tracker
                        if otm2_ce and otm2_pe and otm4_ce and otm4_pe:
                            tracker_legs = [
                                {"symbol": otm2_ce.get("symbol"), "action": "SELL", "quantity": self.quantity},
                                {"symbol": otm2_pe.get("symbol"), "action": "SELL", "quantity": self.quantity},
                            ]

                            # Filter the execution legs to only include short ('SELL') legs before calling tracker.add_legs()
                            # to prevent false premature exits triggered by protective buy legs.
                            entry_prices = [
                                safe_float(otm2_ce.get("ltp")),
                                safe_float(otm2_pe.get("ltp"))
                            ]

                            self.tracker.add_legs(tracker_legs, entry_prices, side="SELL")

                            # Also store the buy legs so we can close them later
                            # The OptionPositionTracker strictly expects open_legs to manage SL/TP.
                            # So we manually append the protective buy legs, BUT without entry_price
                            # wait, no, OptionPositionTracker will include them in PnL if they are in open_legs.
                            # Wait! Memory says: "ensure you filter the execution legs to only include short ('SELL') legs before calling tracker.add_legs(). Failure to do so may cause false premature exits triggered by protective buy legs."
                            # But wait, we still need to close the BUY legs when we close the position!
                            # Let's add them to tracker's open_legs but set action="BUY" so they are tracked but SL/TP will be based only on premium.
                            # Wait, the memory is very specific: "filter the execution legs to only include short ('SELL') legs before calling tracker.add_legs()."
                            # Let's only add SELL legs to `tracker.add_legs()`. But we need to keep track of BUY legs for `_close_position()`.
                            # We can just extend `self.tracker.open_legs` with the BUY legs manually but set a flag so `should_exit` ignores them?
                            # Let's look at OptionPositionTracker:
                            # `for leg in self.open_legs: ... if leg["action"].upper() == "SELL": pnl += (entry - curr); total_initial_premium_abs += entry ... else: pnl += (curr - entry); total_initial_premium_abs += entry`
                            # Ah, the memory meant to literally only add the SELL legs.
                            # So I will store the BUY legs in a separate list `self.protective_legs` and close them in `_close_position`.

                            self.protective_legs = [
                                {"symbol": otm4_ce.get("symbol"), "action": "BUY", "quantity": self.quantity},
                                {"symbol": otm4_pe.get("symbol"), "action": "BUY", "quantity": self.quantity},
                            ]

                            self.limiter.record()
                            self.entered_today = True
                            self.logger.info(f"Position tracking started with legs: {tracker_legs} and protective legs: {self.protective_legs}")
                        else:
                            self.logger.error("Failed to map OTM2/OTM4 offsets to symbols for tracking. Chain data might be incomplete.")

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(self.sleep_seconds)

    # Override _close_position to also close protective_legs
    def _close_position(self, chain, exit_reason):
        self.logger.info(f"event=trade action=CLOSE reason={exit_reason}")

        # Merge tracker open_legs and protective_legs
        all_legs = self.tracker.open_legs + getattr(self, "protective_legs", [])

        # Close each individually
        for leg in all_legs:
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            try:
                resp = self.client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg.get("quantity", self.quantity),
                    position_size=leg.get("quantity", self.quantity)
                )
                self.logger.info(f"Trade response for leg {leg['symbol']}: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()
        if hasattr(self, "protective_legs"):
            self.protective_legs = []

if __name__ == "__main__":
    NiftyIronCondor().run()
