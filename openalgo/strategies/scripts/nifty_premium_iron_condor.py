#!/usr/bin/env python3
"""
Nifty Premium Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if straddle premium > 120. Sells OTM2, Buys OTM4.
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
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "nifty_premium_ic")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "10"))

        # Parameters
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))
        self.entry_start_time = dt_time(10, 0)
        self.entry_end_time = dt_time(14, 30)
        self.exit_time = dt_time(15, 15)

        # Trackers and limiters
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.expiry_date = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0
        self.ledger = TradeLedger(f"/log/strategies/{self.strategy_name}_trades.csv")

    def ensure_expiry(self):
        """Fetches and caches the nearest expiry date."""
        now = time.time()
        if self.expiry_date and (now - self.last_expiry_refresh) < self.expiry_refresh_sec:
            return

        try:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res.get("status") == "success" and "data" in res:
                dates = res["data"]
                self.expiry_date = choose_nearest_expiry(dates)
                self.last_expiry_refresh = now
                self.logger.info(f"Resolved nearest expiry: {self.expiry_date}")
            else:
                self.logger.warning(f"Failed to fetch expiry: {res.get('message', 'Unknown error')}")
        except Exception as e:
            self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        """Checks time-based rules and trade limits."""
        now_time = datetime.now().time()

        if now_time < self.entry_start_time or now_time > self.entry_end_time:
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        """Closes all open legs individually and clears the tracker."""
        self.logger.info(f"Closing position. Reason: {reason}")

        for leg in self.tracker.open_legs:
            # Reverse the action
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            symbol = leg["symbol"]
            qty = leg.get("quantity", self.quantity)

            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=qty,
                    position_size=0
                )
                self.logger.info(f"event=trade action={close_action} symbol={symbol} response={resp}")
                self.ledger.append({
                    "timestamp": datetime.now().isoformat(),
                    "side": close_action,
                    "reason": reason,
                    "details": f"Symbol: {symbol}, Response: {resp}"
                })
            except Exception as e:
                self.logger.error(f"Error closing leg {symbol}: {e}")

        self.tracker.clear()

    def get_atm_strike(self, chain_resp):
        """Extracts ATM strike directly from chain response."""
        atm_strike = chain_resp.get("atm_strike")
        if atm_strike is not None:
            return float(atm_strike)

        # Fallback to finding "ATM" label
        chain = chain_resp.get("chain", [])
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM" or item.get("pe", {}).get("label") == "ATM":
                return item["strike"]
        return None

    def calculate_straddle_premium(self, chain, atm_strike):
        """Calculates premium of ATM CE + ATM PE."""
        for item in chain:
            if item["strike"] == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                return ce_ltp + pe_ltp
        return 0.0

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} Strategy Loop...")

        while True:
            try:
                if not is_market_open(exchange="NSE"):
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain data: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EOD Square-off
                now_time = datetime.now().time()
                if now_time >= self.exit_time and self.tracker.open_legs:
                    self._close_position(chain, "eod_square_off")
                    time.sleep(self.sleep_seconds)
                    continue

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # INDICATORS
                atm_strike = self.get_atm_strike(chain_resp)
                if not atm_strike:
                    continue

                straddle_premium = self.calculate_straddle_premium(chain, atm_strike)
                spot = chain_resp.get("underlying_ltp", 0)

                self.logger.info(format_kv(
                    spot=spot,
                    atm=atm_strike,
                    premium=f"{straddle_premium:.2f}",
                    positions=len(self.tracker.open_legs)
                ))

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    signal = straddle_premium > self.min_straddle_premium

                    if self.debouncer.edge("ic_entry", signal):
                        self.logger.info(f"Signal active. Straddle premium {straddle_premium:.2f} > {self.min_straddle_premium}")

                        # Note: BUY legs first for margin efficiency
                        legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.options_exchange,
                            expiry_date=self.expiry_date,
                            legs=legs
                        )

                        self.logger.info(f"event=trade action=ENTRY response={resp}")
                        self.limiter.record()

                        # Find entry prices for the tracking (specifically the short legs for SL/TP tracking)
                        # We need to extract the exact symbols we entered to track them properly
                        if resp.get("status") == "success":
                            # Typically we should parse the response for actual symbols and executed prices.
                            # Since OpenAlgo's mock/sim response might not give back exact symbols immediately in the response,
                            # we will extract them from the current chain data based on the offsets.

                            entered_short_legs = []
                            entry_prices = []

                            # Helper to find symbol and ltp by offset
                            def get_option_by_offset(chain, offset, opt_type):
                                for item in chain:
                                    opt_data = item.get(opt_type.lower(), {})
                                    if opt_data.get("label") == offset:
                                        return opt_data
                                return None

                            for leg in legs:
                                opt_data = get_option_by_offset(chain, leg["offset"], leg["option_type"])
                                if opt_data and leg["action"] == "SELL":
                                    # We only add SELL legs to the tracker to monitor credit
                                    entered_short_legs.append({
                                        "symbol": opt_data.get("symbol"),
                                        "action": "SELL",
                                        "quantity": leg["quantity"]
                                    })
                                    entry_prices.append(safe_float(opt_data.get("ltp")))

                            if entered_short_legs:
                                self.tracker.add_legs(entered_short_legs, entry_prices, side="SELL")
                                self.logger.info(f"Tracking {len(entered_short_legs)} short legs for exits.")

                        self.ledger.append({
                            "timestamp": datetime.now().isoformat(),
                            "side": "ENTRY",
                            "reason": "premium_threshold",
                            "details": f"Straddle: {straddle_premium}, Resp: {resp}"
                        })

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
