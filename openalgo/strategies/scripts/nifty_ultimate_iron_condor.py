#!/usr/bin/env python3
"""
Nifty Ultimate Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120, sells OTM2/buys OTM4 with 40% SL, 50% TP, and 45-min max hold.
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
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyUltimateIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "30"), 30)
        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "120"), 120)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )

        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.today_date = datetime.now().date()

        self.all_open_legs = []

        self.logger.info(f"Initialized {self.strategy_name} for {self.underlying}")

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    expiries = res.get("data")
                    self.expiry = choose_nearest_expiry(expiries)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                else:
                    self.logger.warning(f"Failed to fetch expiries: {res}")
            except Exception as e:
                self.logger.error(f"Error resolving expiry: {e}")

    def can_trade(self):
        now = datetime.now()

        if now.date() != self.today_date:
            self.today_date = now.date()
            self.entered_today = False
            self.tracker.clear()
            self.all_open_legs = []

        if self.entered_today:
            return False

        # Entry window: 10:00 AM to 2:30 PM
        current_time = now.time()
        start_time = datetime.strptime("10:00:00", "%H:%M:%S").time()
        end_time = datetime.strptime("14:30:00", "%H:%M:%S").time()

        if not (start_time <= current_time <= end_time):
            return False

        return self.limiter.allow()

    def get_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" and pe.get("label") == "ATM":
                ce_ltp = safe_float(ce.get("ltp"), 0.0)
                pe_ltp = safe_float(pe.get("ltp"), 0.0)
                if ce_ltp > 0 and pe_ltp > 0:
                    return ce_ltp + pe_ltp
        return 0.0

    def _close_position(self, chain, exit_reason):
        if not self.all_open_legs:
            self.tracker.clear()
            return

        self.logger.info(f"Closing position. Reason: {exit_reason}")

        for leg in self.all_open_legs:
            # We reverse the action. Buy -> SELL, Sell -> BUY
            close_action = "BUY" if leg.get("action", "SELL") == "SELL" else "SELL"
            symbol = leg.get("symbol")
            qty = leg.get("quantity", self.quantity)
            if symbol:
                try:
                    resp = self.api_client.placesmartorder(
                        strategy=self.strategy_name,
                        symbol=symbol,
                        action=close_action,
                        exchange=self.options_exchange,
                        pricetype="MARKET",
                        product=self.product,
                        quantity=qty,
                        position_size=0 # 0 to close position
                    )
                    self.logger.info(format_kv(event="trade", symbol=symbol, action=close_action, status="CLOSED", response=str(resp)))
                except Exception as e:
                    self.logger.error(f"Error closing leg {symbol}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def get_option_by_offset(self, chain, opt_type, offset):
        for item in chain:
            opt = item.get(opt_type.lower(), {})
            if opt.get("label") == offset:
                return opt
        return None

    def run(self):
        while True:
            try:
                if not is_market_open():
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)

                # Time-based square off at 3:15 PM
                now = datetime.now().time()
                eod_exit_time = datetime.strptime("15:15:00", "%H:%M:%S").time()

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    if now >= eod_exit_time:
                        self._close_position(chain, "EOD Square-off")
                    else:
                        exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                        if exit_now:
                            self._close_position(chain, exit_reason)
                    time.sleep(self.sleep_seconds)
                    continue
                else:
                    if self.all_open_legs:
                        # Tracker clear but we have open legs? Should not happen normally unless tracker was cleared externally
                        self._close_position(chain, "Sync Issue")

                # If after EOD exit time, don't enter new positions
                if now >= eod_exit_time:
                    time.sleep(self.sleep_seconds)
                    continue

                # CALCULATE INDICATORS
                straddle_premium = self.get_straddle_premium(chain)

                # ENTRY LOGIC
                can_trade_now = self.can_trade()
                condition = straddle_premium > 120

                # Signal edge detection combined with time condition
                signal = self.debouncer.edge("entry_signal", condition and can_trade_now)

                if signal and not self.tracker.open_legs and not self.all_open_legs:
                    self.logger.info(format_kv(spot=spot, straddle_premium=straddle_premium, signal="ENTER_IRON_CONDOR"))

                    otm2_ce = self.get_option_by_offset(chain, "CE", "OTM2")
                    otm2_pe = self.get_option_by_offset(chain, "PE", "OTM2")
                    otm4_ce = self.get_option_by_offset(chain, "CE", "OTM4")
                    otm4_pe = self.get_option_by_offset(chain, "PE", "OTM4")

                    if not (otm2_ce and otm2_pe and otm4_ce and otm4_pe):
                        self.logger.warning("Could not find required strikes for Iron Condor.")
                        time.sleep(self.sleep_seconds)
                        continue

                    # multi-leg request
                    legs_request = [
                        {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                        {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                        {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                    ]

                    try:
                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.options_exchange,
                            expiry_date=self.expiry,
                            legs=legs_request
                        )
                        self.logger.info(f"Trade response: {resp}")

                        # Set entered flag
                        self.entered_today = True
                        self.limiter.record()

                        # Prepare legs for tracking
                        self.all_open_legs = [
                            {"symbol": otm4_ce.get("symbol"), "action": "BUY", "quantity": self.quantity},
                            {"symbol": otm4_pe.get("symbol"), "action": "BUY", "quantity": self.quantity},
                            {"symbol": otm2_ce.get("symbol"), "action": "SELL", "quantity": self.quantity},
                            {"symbol": otm2_pe.get("symbol"), "action": "SELL", "quantity": self.quantity},
                        ]

                        # Only track short legs for TP/SL
                        short_legs = [
                            {"symbol": otm2_ce.get("symbol"), "action": "SELL", "entry_price": safe_float(otm2_ce.get("ltp"))},
                            {"symbol": otm2_pe.get("symbol"), "action": "SELL", "entry_price": safe_float(otm2_pe.get("ltp"))}
                        ]

                        entry_prices = {
                            otm2_ce.get("symbol"): safe_float(otm2_ce.get("ltp")),
                            otm2_pe.get("symbol"): safe_float(otm2_pe.get("ltp"))
                        }

                        self.tracker.add_legs(short_legs, entry_prices, side="SELL")

                    except Exception as e:
                        self.logger.error(f"Error placing entry order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
