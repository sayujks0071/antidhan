#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if straddle premium > 120. Sells OTM2, Buys OTM4.
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
        self.strategy_name = os.getenv("STRATEGY_NAME", "nifty_iron_condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "300"))

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=1, max_per_hour=1, cooldown_seconds=60)
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_check = 0
        self.entered_today = False
        self.entry_date = None
        self.buy_legs = []

        self.logger.info(f"Initialized {self.strategy_name} for {self.underlying}")

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_check = now
                    self.logger.info(f"Using expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry: {e}")

    def can_trade(self):
        now = datetime.now()

        # Reset daily tracking
        if self.entry_date != now.date():
            self.entered_today = False
            self.entry_date = now.date()

        if self.entered_today:
            return False

        # Time filter: Enters after 10 AM, exits by 3:15 PM
        current_time = now.time()
        start_time = datetime.strptime("10:00", "%H:%M").time()
        end_time = datetime.strptime("15:15", "%H:%M").time()

        if not (start_time <= current_time < end_time):
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        self.logger.info(f"event=exit reason={reason}")

        # We must extract the actual symbols and actions to close, reversing the original actions
        # Memory constraint: To properly close an open multi-leg position tracked by OptionPositionTracker,
        # do NOT use optionsmultiorder with relative offsets. Close each individually.
        all_legs_to_close = self.tracker.open_legs + self.buy_legs

        for leg in all_legs_to_close:
            symbol = leg.get("symbol")
            if not symbol:
                continue

            # Reverse action
            close_action = "BUY" if leg.get("side", leg.get("action")) == "SELL" else "SELL"

            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0
                )
                self.logger.info(f"event=close_leg symbol={symbol} action={close_action} resp={resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {symbol}: {e}")

        self.tracker.clear()
        self.buy_legs = []

    def _get_straddle_premium(self, chain):
        atm_ce = None
        atm_pe = None
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM":
                atm_ce = ce
            if pe.get("label") == "ATM":
                atm_pe = pe

        if atm_ce and atm_pe:
            return safe_float(atm_ce.get("ltp")) + safe_float(atm_pe.get("ltp"))
        return 0.0

    def get_option_by_label(self, chain, label, option_type):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == label:
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

                now = datetime.now().time()
                eod_time = datetime.strptime("15:15", "%H:%M").time()

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    # EOD Square-off
                    if now >= eod_time:
                        self._close_position(chain, "EOD_squareoff")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    straddle_premium = self._get_straddle_premium(chain)

                    self.logger.info(format_kv(spot=chain_resp.get("underlying_ltp"), premium=straddle_premium))

                    cond = (straddle_premium > 120.0)

                    # Entry edge
                    if self.debouncer.edge("entry_cond", cond):
                        self.logger.info(f"event=signal signal=IRON_CONDOR premium={straddle_premium}")

                        # Prepare multi-order payload
                        # Rules: Buy legs first, then sell legs
                        legs_req = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        try:
                            resp = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.underlying_exchange,
                                expiry_date=self.expiry,
                                legs=legs_req
                            )
                            self.logger.info(f"event=trade resp={resp}")

                            self.limiter.record()
                            self.entered_today = True

                            # For OptionPositionTracker, only track the short legs to manage SL/TP properly
                            # Also we need to get their actual entry prices and symbols
                            sell_legs = []
                            entry_prices = []

                            otm2_ce = self.get_option_by_label(chain, "OTM2", "CE")
                            otm2_pe = self.get_option_by_label(chain, "OTM2", "PE")
                            otm4_ce = self.get_option_by_label(chain, "OTM4", "CE")
                            otm4_pe = self.get_option_by_label(chain, "OTM4", "PE")

                            if otm2_ce and otm2_pe and otm4_ce and otm4_pe:
                                # Track short legs for SL/TP management
                                sell_legs.append({"symbol": otm2_ce.get("symbol"), "option_type": "CE", "side": "SELL"})
                                entry_prices.append(safe_float(otm2_ce.get("ltp")))

                                sell_legs.append({"symbol": otm2_pe.get("symbol"), "option_type": "PE", "side": "SELL"})
                                entry_prices.append(safe_float(otm2_pe.get("ltp")))

                                self.tracker.add_legs(sell_legs, entry_prices, side="SELL")

                                # Store the buy legs separately so we can close them later
                                # We don't want them in the tracker because protective wings usually
                                # hit SL quickly due to theta decay, prematurely exiting the trade.
                                self.buy_legs.extend([
                                    {
                                        "symbol": otm4_ce.get("symbol"),
                                        "option_type": "CE",
                                        "side": "BUY",
                                        "entry_price": safe_float(otm4_ce.get("ltp")),
                                        "entry_time": time.time()
                                    },
                                    {
                                        "symbol": otm4_pe.get("symbol"),
                                        "option_type": "PE",
                                        "side": "BUY",
                                        "entry_price": safe_float(otm4_pe.get("ltp")),
                                        "entry_time": time.time()
                                    }
                                ])
                            else:
                                self.logger.error("Could not find all required option legs in chain to track")

                        except Exception as e:
                            self.logger.error(f"Error placing order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
