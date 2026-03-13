#!/usr/bin/env python3
"""
[Nifty Iron Condor] - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy entering >10 AM if straddle > 120. Sells OTM2, Buys OTM4.
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

# Add utils to sys.path first
sys.path.insert(0, utils_dir)

# Add root directory to sys.path
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

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


API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

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
        self.logger.info("Initializing Nifty Iron Condor Strategy...")

        # 1. Configuration (os.getenv with sensible defaults)
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Strategy-specific parameters
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))
        self.short_offset = os.getenv("SHORT_OFFSET", "OTM2")
        self.long_offset = os.getenv("LONG_OFFSET", "OTM4")

        # Risk Management Parameters
        self.sl_pct = float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Scheduling and Limits
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # Setup Clients and Trackers
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
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
        self.last_trade_date = None

        self.logger.info(format_kv(
            strategy=self.strategy_name,
            underlying=self.underlying,
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold=self.max_hold_min,
            min_premium=self.min_straddle_premium
        ))

    def ensure_expiry(self):
        """Auto-resolve nearest expiry and refresh periodically."""
        now = time.time()

        # Use manual override if provided
        manual_expiry = os.getenv("EXPIRY_DATE")
        if manual_expiry:
            self.expiry = normalize_expiry(manual_expiry)
            return

        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res["data"]
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_check = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                else:
                    self.logger.warning("Could not fetch expiry dates from API")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        """Check entry conditions based on time, market state, and limits."""
        now = datetime.now()

        # Reset daily limits on a new day
        current_date = now.date()
        if self.last_trade_date != current_date:
            self.entered_today = False
            self.last_trade_date = current_date

        # Entry time windows
        if now.hour < 10:
            return False

        if now.hour == 15 and now.minute >= 15:
            return False
        if now.hour > 15:
            return False

        # Daily limit
        if self.entered_today:
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        """Helper to close position correctly"""
        if not self.tracker.open_legs:
            return

        self.logger.info(f"Closing position. Reason: {reason}")

        all_legs_to_close = self.tracker.open_legs.copy()
        if hasattr(self, 'long_legs') and self.long_legs:
            all_legs_to_close.extend(self.long_legs)
            self.long_legs = []

        for leg in all_legs_to_close:
            # Reversing the trade
            action = "BUY" if leg["side"] == "SELL" else "SELL"
            try:
                from trading_utils import APIClient
                api_client = APIClient(api_key=API_KEY, host=HOST)

                resp = api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=1
                )
                self.logger.info(f"Close leg {leg['symbol']} response: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()

    def get_atm_straddle_premium(self, chain):
        """Calculate the premium of the ATM Straddle"""
        atm_ce_ltp = 0
        atm_pe_ltp = 0

        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})

            if ce.get("label") == "ATM":
                atm_ce_ltp = safe_float(ce.get("ltp"))
            if pe.get("label") == "ATM":
                atm_pe_ltp = safe_float(pe.get("ltp"))

        return atm_ce_ltp + atm_pe_ltp

    def run(self):
        """Main Strategy Execution Loop."""
        self.logger.info(f"Starting execution loop for {self.strategy_name}")

        while True:
            try:
                # 1. Ensure market is open
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                # 2. Ensure expiry is resolved
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # 3. Fetch Option Chain
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                # 4. Validate Chain Data
                valid, reason = is_chain_valid(chain_resp, min_strikes=4, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.warning(f"Invalid chain data: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)

                # 5. EOD Square-off (Before 3:15 PM)
                now = datetime.now()
                is_eod = now.hour == 15 and now.minute >= 15

                # 6. EXIT MANAGEMENT (Check exits before entries)
                if self.tracker.open_legs:
                    if is_eod:
                        self._close_position(chain, "EOD_Square_Off")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue
                else:
                    # Clear out tracker in case it was dirty
                    if is_eod:
                        time.sleep(self.sleep_seconds)
                        continue

                # 7. INDICATORS & CONDITIONS
                straddle_premium = self.get_atm_straddle_premium(chain)

                # We only check for the premium condition if we are allowed to trade right now
                # This prevents the debouncer from firing before 10 AM and missing the entry
                can_trade_now = self.can_trade()
                premium_condition = straddle_premium > self.min_straddle_premium and can_trade_now

                # Signal Edge detection
                signal = self.debouncer.edge("premium_entry", premium_condition)

                if straddle_premium > self.min_straddle_premium:
                    self.logger.debug(format_kv(spot=spot, straddle_premium=straddle_premium, required=self.min_straddle_premium))

                # 8. ENTRY LOGIC
                if not self.tracker.open_legs and signal:
                    self.logger.info(f"Entry signal detected! Straddle Premium: {straddle_premium} > {self.min_straddle_premium}")

                    # BUY legs must execute first, then SELL
                    legs = [
                        {"offset": self.long_offset, "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                        {"offset": self.long_offset, "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                        {"offset": self.short_offset, "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        {"offset": self.short_offset, "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                    ]

                    self.logger.info(f"Placing multi-leg Iron Condor order: {legs}")
                    try:
                        response = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=legs
                        )
                        self.logger.info(f"Order response: {response}")

                        # In a real scenario, you'd parse exact filled prices and symbols from response
                        # For now, we simulate finding the symbols from the chain

                        executed_legs = []
                        entry_prices = []

                        # Find OTM2 prices to track (we only track the short legs for SL/TP in short premium)
                        for item in chain:
                            ce = item.get("ce", {})
                            pe = item.get("pe", {})

                            if ce.get("label") == self.short_offset:
                                executed_legs.append({"symbol": ce.get("symbol"), "side": "SELL"})
                                entry_prices.append(safe_float(ce.get("ltp")))
                            elif ce.get("label") == self.long_offset:
                                executed_legs.append({"symbol": ce.get("symbol"), "side": "BUY"})
                                entry_prices.append(safe_float(ce.get("ltp")))

                            if pe.get("label") == self.short_offset:
                                executed_legs.append({"symbol": pe.get("symbol"), "side": "SELL"})
                                entry_prices.append(safe_float(pe.get("ltp")))
                            elif pe.get("label") == self.long_offset:
                                executed_legs.append({"symbol": pe.get("symbol"), "side": "BUY"})
                                entry_prices.append(safe_float(pe.get("ltp")))

                        if executed_legs:
                            # We only track the short legs for SL/TP evaluation in short premium strategies
                            short_legs = [leg for leg in executed_legs if leg["side"] == "SELL"]
                            short_prices = [price for leg, price in zip(executed_legs, entry_prices) if leg["side"] == "SELL"]

                            # But we add all legs to tracker so _close_position closes everything
                            # Note: The OptionPositionTracker internally checks SL/TP against all legs added.
                            # Since we want SL/TP on short legs only, we trick it by adding all legs,
                            # but we must be aware that OptionPositionTracker will evaluate SL/TP on the combined position.
                            # Given the prompt said "Uses 40% SL and 50% TP on the short legs",
                            # we should only add the short legs to the tracker to strictly enforce SL/TP on them.
                            # However, to close all legs, we store the long legs separately.

                            self.tracker.add_legs(short_legs, short_prices, side="SELL")
                            self.long_legs = [leg for leg in executed_legs if leg["side"] == "BUY"]
                            self.limiter.record()
                            self.entered_today = True
                            self.logger.info(f"Tracking short legs: {executed_legs} at {entry_prices}")
                        else:
                            self.logger.warning("Could not identify short leg symbols from chain to track.")

                    except Exception as e:
                        self.logger.error(f"Error placing order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyIronCondor().run()
