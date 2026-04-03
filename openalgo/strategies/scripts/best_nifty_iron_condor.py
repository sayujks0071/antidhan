#!/usr/bin/env python3
"""
[best_nifty_iron_condor.py] - NIFTY Options (OpenAlgo Web UI Compatible)
Intraday Nifty Iron Condor: Enter after 10 AM, premium > 120, Sell OTM2/Buy OTM4, strict SL/TP and 45-min hold.
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
    from strategy_common import SignalDebouncer, TradeLimiter, format_kv
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# API Key retrieval (MANDATORY - place after configuration section)
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


class StrategyClass:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "10"))

        # SL / TP / Max Hold
        self.sl_pct = float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Delays / Retries
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "15"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # Rate Limiting
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "2")) # Usually 1 full trade
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

        # Other Strategy specific constraints
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )

        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.all_open_legs = []  # Keep track of all open legs to exit individually

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        self.expiry = choose_nearest_expiry(dates)
                        self.last_expiry_refresh = now
                        self.logger.info(f"Resolved expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error resolving expiry: {e}")

    def _get_atm_straddle_premium(self, chain):
        atm_ce = 0.0
        atm_pe = 0.0
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM":
                atm_ce = safe_float(ce.get("ltp"))
            if pe.get("label") == "ATM":
                atm_pe = safe_float(pe.get("ltp"))
            if atm_ce > 0 and atm_pe > 0:
                break
        return atm_ce + atm_pe

    def _get_legs_ltp(self, chain, offsets):
        """
        Returns a dict of ltp mapping for offsets like {'OTM2_CE': ltp, 'OTM4_PE': ltp}
        """
        prices = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") in offsets:
                prices[f"{ce.get('label')}_CE"] = safe_float(ce.get("ltp"))
            if pe.get("label") in offsets:
                prices[f"{pe.get('label')}_PE"] = safe_float(pe.get("ltp"))
        return prices

    def _get_leg_symbols(self, chain, offsets):
        symbols = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") in offsets:
                symbols[f"{ce.get('label')}_CE"] = ce.get("symbol")
            if pe.get("label") in offsets:
                symbols[f"{pe.get('label')}_PE"] = pe.get("symbol")
        return symbols

    def _close_position(self, chain, reason):
        """Close legs via individual placesmartorder calls to ensure reliable exit."""
        self.logger.info(f"Closing position. Reason: {reason}")
        if not self.all_open_legs:
            self.tracker.clear()
            return

        # Priority: BUY legs first to cover shorts, then SELL legs to close longs
        buy_to_cover = [leg for leg in self.all_open_legs if leg.get('action') == 'SELL']
        sell_to_close = [leg for leg in self.all_open_legs if leg.get('action') == 'BUY']

        ordered_close_legs = buy_to_cover + sell_to_close

        for leg in ordered_close_legs:
            # reverse action
            close_action = "BUY" if leg.get("action") == "SELL" else "SELL"
            try:
                self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg.get("symbol"),
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0 # Exit
                )
                self.logger.info(f"Trade response: Placed close order for {leg.get('symbol')} action={close_action}")
            except Exception as e:
                self.logger.error(f"Error closing {leg.get('symbol')}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def can_trade(self):
        now = datetime.now()
        # Time constraints: 10:00 AM to 3:15 PM
        if now.hour < 10 or (now.hour == 15 and now.minute >= 15) or now.hour >= 16:
            return False

        if self.entered_today:
            return False

        return self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} strategy")
        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                now = datetime.now()
                # End of day square-off before 3:15 PM
                if now.hour == 15 and now.minute >= 15:
                    if self.tracker.open_legs:
                        self._close_position([], "EOD_SQUAREOFF")
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp"))

                # 1. EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, _legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # 2. CALCULATE INDICATORS
                straddle_premium = self._get_atm_straddle_premium(chain)

                self.logger.info(format_kv(spot=underlying_ltp, straddle=straddle_premium, open_legs=len(self.all_open_legs)))

                # 3. ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    # Iron Condor Conditions:
                    # After 10 AM, premium > 120
                    condition = straddle_premium > self.min_straddle_premium

                    if self.debouncer.edge("enter_ic", condition):
                        self.logger.info(f"Entry condition met: Straddle premium {straddle_premium} > {self.min_straddle_premium}")

                        # Prepare multi-leg order: BUY before SELL for margin
                        legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        try:
                            # Place multi-leg order
                            res = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.underlying_exchange,
                                expiry_date=self.expiry,
                                legs=legs
                            )

                            if res and res.get("status") == "success":
                                self.logger.info(f"event=trade Trade response: Successfully entered Iron Condor.")
                                self.entered_today = True
                                self.limiter.record()

                                # Track short legs for SL/TP
                                short_legs = [
                                    {"symbol": l.get("symbol", ""), "action": "SELL"}
                                    for l in res.get("data", []) if l.get("action") == "SELL"
                                ]

                                # For precise tracking, get entry prices
                                prices = self._get_legs_ltp(chain, ["OTM2", "OTM4"])
                                entry_prices = []
                                for l in short_legs:
                                    # Since optionsmultiorder doesn't return prices, we fallback to our ltp lookup
                                    entry_prices.append(0.0) # Will be resolved if we can map it

                                # Instead of trusting multiorder response to give prices, we track them from the chain
                                actual_short_legs = []
                                actual_short_prices = []
                                leg_symbols = self._get_leg_symbols(chain, ["OTM2", "OTM4"])

                                # Update tracking
                                if "OTM2_CE" in leg_symbols and "OTM2_CE" in prices:
                                    actual_short_legs.append({"symbol": leg_symbols["OTM2_CE"], "action": "SELL"})
                                    actual_short_prices.append(prices["OTM2_CE"])
                                if "OTM2_PE" in leg_symbols and "OTM2_PE" in prices:
                                    actual_short_legs.append({"symbol": leg_symbols["OTM2_PE"], "action": "SELL"})
                                    actual_short_prices.append(prices["OTM2_PE"])

                                if len(actual_short_legs) > 0:
                                    self.tracker.add_legs(actual_short_legs, actual_short_prices, side="SELL")

                                # Keep all open legs to close individually later
                                self.all_open_legs = []
                                if "OTM4_CE" in leg_symbols:
                                    self.all_open_legs.append({"symbol": leg_symbols["OTM4_CE"], "action": "BUY"})
                                if "OTM4_PE" in leg_symbols:
                                    self.all_open_legs.append({"symbol": leg_symbols["OTM4_PE"], "action": "BUY"})
                                self.all_open_legs.extend(actual_short_legs)

                            else:
                                self.logger.error(f"Failed to enter Iron Condor: {res}")

                        except Exception as e:
                            self.logger.error(f"Exception placing multi-order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
