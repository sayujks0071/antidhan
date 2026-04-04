#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120. Sells OTM2, Buys OTM4.
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


class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "best_nifty_iron_condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "120"), 120)
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "20"), 20)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)

        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
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

        self.expiry_date = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0
        self.entered_today = False

        self.logger.info(f"Initialized {self.strategy_name} with SL={self.sl_pct}%, TP={self.tp_pct}%")

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry_date or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res.get("status") == "success" and res.get("data"):
                self.expiry_date = choose_nearest_expiry(res["data"])
                self.last_expiry_refresh = now
                self.logger.info(f"Selected Expiry: {self.expiry_date}")
            else:
                self.logger.error("Failed to fetch expiry dates")

    def can_trade(self):
        now = datetime.now()
        # Enters after 10 AM, don't enter after 3 PM (15:00)
        if now.hour < 10 or now.hour >= 15:
            return False

        if self.entered_today:
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        self.logger.info(format_kv(event="trade", action="EXIT", reason=reason))

        # Sort legs to BUY to cover short legs first, then SELL to close long legs
        # For margin efficiency
        sorted_legs = sorted(self.tracker.open_legs, key=lambda l: 0 if l["action"] == "SELL" else 1)

        for leg in sorted_legs:
            # Reverse action
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            self.logger.info(f"Closing leg: {leg['symbol']} -> {close_action}")

            # Use placesmartorder to close each leg individually
            self.client.placesmartorder(
                strategy=self.strategy_name,
                symbol=leg["symbol"],
                action=close_action,
                exchange=self.options_exchange,
                pricetype="MARKET",
                product=self.product,
                quantity=leg["quantity"],
                position_size=0
            )
            time.sleep(0.5) # Prevent rate limits

        self.tracker.clear()

    def run(self):
        while True:
            try:
                if not is_market_open():
                    # Reset daily flag when market is closed
                    now = datetime.now()
                    if now.hour >= 16:
                        self.entered_today = False
                    time.sleep(self.sleep_seconds)
                    continue

                # EOD Square-off before 3:15 PM (15:15)
                now = datetime.now()
                if now.hour == 15 and now.minute >= 15 and self.tracker.open_legs:
                    self.logger.info("EOD Square-off triggered")
                    self._close_position([], "eod_squareoff")
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry_date:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry_date,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS
                atm_strike = None
                atm_ce_ltp = 0
                atm_pe_ltp = 0

                # Extract options we need for Iron Condor (OTM2 sell, OTM4 buy)
                otm2_ce = None
                otm2_pe = None
                otm4_ce = None
                otm4_pe = None

                for item in chain:
                    ce = item.get("ce", {})
                    pe = item.get("pe", {})

                    if ce.get("label") == "ATM":
                        atm_strike = item.get("strike")
                        atm_ce_ltp = safe_float(ce.get("ltp"))
                        atm_pe_ltp = safe_float(pe.get("ltp"))

                    if ce.get("label") == "OTM2": otm2_ce = ce
                    if pe.get("label") == "OTM2": otm2_pe = pe
                    if ce.get("label") == "OTM4": otm4_ce = ce
                    if pe.get("label") == "OTM4": otm4_pe = pe

                straddle_premium = atm_ce_ltp + atm_pe_ltp

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    # Iron Condor entry condition: straddle premium > 120
                    signal = self.debouncer.edge("ic_entry", straddle_premium > 120)

                    if signal and otm2_ce and otm2_pe and otm4_ce and otm4_pe:
                        self.logger.info(format_kv(
                            event="trade",
                            action="ENTRY",
                            strategy="Iron Condor",
                            straddle_premium=straddle_premium
                        ))

                        # Define legs: BUY wings first, then SELL body
                        legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry_date,
                            legs=legs
                        )

                        if resp and resp.get("status") == "success":
                            self.limiter.record()
                            self.entered_today = True

                            # Track position
                            # Extract executed prices from our chain data as a proxy for entry prices
                            entry_prices = [
                                safe_float(otm4_ce.get("ltp")),
                                safe_float(otm4_pe.get("ltp")),
                                safe_float(otm2_ce.get("ltp")),
                                safe_float(otm2_pe.get("ltp"))
                            ]

                            tracker_legs = [
                                {"symbol": otm4_ce.get("symbol"), "action": "BUY", "quantity": self.quantity},
                                {"symbol": otm4_pe.get("symbol"), "action": "BUY", "quantity": self.quantity},
                                {"symbol": otm2_ce.get("symbol"), "action": "SELL", "quantity": self.quantity},
                                {"symbol": otm2_pe.get("symbol"), "action": "SELL", "quantity": self.quantity}
                            ]

                            self.tracker.add_legs(tracker_legs, entry_prices, side="SELL")
                            self.logger.info("Successfully opened Iron Condor")
                        else:
                            self.logger.error(f"Failed to open Iron Condor: {resp}")

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
