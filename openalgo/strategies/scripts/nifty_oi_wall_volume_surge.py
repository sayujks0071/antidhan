#!/usr/bin/env python3
"""
Nifty OI Wall + Volume Surge - NIFTY Options (OpenAlgo Web UI Compatible)
Buys CE on bounce off Put OI support, PE on rejection from Call OI resistance.
"""
import os
import sys
import time
from datetime import datetime, timedelta

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


class NiftyOIWallStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Config via os.getenv
        self.strategy_name = os.getenv("STRATEGY_NAME", "OIWallVolume")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"))
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = safe_float(os.getenv("SL_PCT", "30.0"))
        self.tp_pct = safe_float(os.getenv("TP_PCT", "60.0"))
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "20"))

        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "15"))
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "5"))
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))
        self.expiry_date = os.getenv("EXPIRY_DATE", "").strip()

        # State
        self.expiry = self.expiry_date
        self.last_expiry_check = 0
        self.current_date = datetime.now().date()
        self.wall_breach_sl_price = None

        # Trackers
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.all_open_legs = []

        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )

    def ensure_expiry(self):
        if self.expiry and (time.time() - self.last_expiry_check < self.expiry_refresh_sec):
            return

        try:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.last_expiry_check = time.time()
                    self.logger.info(f"Selected expiry: {self.expiry}")
        except Exception as e:
            self.logger.error(f"Expiry fetch error: {e}")

    def _close_position(self, exit_reason):
        if not self.all_open_legs:
            return

        self.logger.info(f"event=trade Closing position. Reason: {exit_reason}")

        for leg in self.all_open_legs:
            action = "BUY" if leg["action"] == "SELL" else "SELL"
            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg["quantity"],
                    position_size=0 # Full square off
                )
                self.logger.info(f"Trade response: Closed {leg['symbol']} - {resp}")
            except Exception as e:
                self.logger.error(f"Failed to close leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []
        self.wall_breach_sl_price = None

    def can_trade(self):
        now = datetime.now().time()
        start_time = datetime.strptime("09:30", "%H:%M").time()
        end_time = datetime.strptime("14:30", "%H:%M").time()
        return start_time <= now <= end_time and self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name}...")

        while True:
            try:
                if datetime.now().date() != self.current_date:
                    self.current_date = datetime.now().date()
                    self.limiter = TradeLimiter(
                        max_per_day=self.max_orders_per_day,
                        max_per_hour=self.max_orders_per_hour,
                        cooldown_seconds=self.cooldown_seconds
                    )

                try:
                    market_open = is_market_open()
                except:
                    market_open = True

                if not market_open:
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=True)
                if not valid:
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = safe_float(chain_resp.get("underlying_ltp"))

                # Exit Management First
                now_time = datetime.now().time()
                eod_time = datetime.strptime("15:15", "%H:%M").time()

                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if now_time >= eod_time:
                        exit_now = True
                        exit_reason = "eod_squareoff"

                    # Dynamic SL on wall breach
                    if self.wall_breach_sl_price is not None:
                        action_type = legs[0]["option_type"] if legs else None

                        # We bought CE because of Put Wall. If price drops below wall, exit
                        if action_type == "CE" and spot < self.wall_breach_sl_price:
                            exit_now = True
                            exit_reason = "wall_support_breach"
                        # We bought PE because of Call Wall. If price breaks above wall, exit
                        elif action_type == "PE" and spot > self.wall_breach_sl_price:
                            exit_now = True
                            exit_reason = "wall_resistance_breach"

                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue
                else:
                    if self.all_open_legs and now_time >= eod_time:
                        self._close_position("eod_squareoff")

                # Entry Logic
                if not self.all_open_legs:
                    if self.can_trade():
                        # Find max OI strikes
                        max_ce_oi = 0
                        max_pe_oi = 0
                        ce_wall_strike = 0.0
                        pe_wall_strike = 0.0

                        atm_ce_sym = None
                        atm_pe_sym = None
                        atm_ce_ltp = 0.0
                        atm_pe_ltp = 0.0

                        atm_ce_vol = 0
                        atm_pe_vol = 0

                        for item in chain:
                            strike = safe_float(item.get("strike"))
                            ce = item.get("ce", {})
                            pe = item.get("pe", {})

                            ce_oi = safe_int(ce.get("oi", 0))
                            pe_oi = safe_int(pe.get("oi", 0))

                            if ce_oi > max_ce_oi:
                                max_ce_oi = ce_oi
                                ce_wall_strike = strike

                            if pe_oi > max_pe_oi:
                                max_pe_oi = pe_oi
                                pe_wall_strike = strike

                            if ce.get("label") == "ATM":
                                atm_ce_sym = ce.get("symbol")
                                atm_ce_ltp = safe_float(ce.get("ltp"))
                                atm_ce_vol = safe_int(ce.get("volume", 0))

                            if pe.get("label") == "ATM":
                                atm_pe_sym = pe.get("symbol")
                                atm_pe_ltp = safe_float(pe.get("ltp"))
                                atm_pe_vol = safe_int(pe.get("volume", 0))

                        self.logger.info(format_kv(
                            spot=f"{spot:.2f}",
                            ce_wall=f"{ce_wall_strike:.0f}",
                            pe_wall=f"{pe_wall_strike:.0f}",
                            status="FLAT"
                        ))

                        # Define Bounce Logic
                        bounce_pe_wall = abs(spot - pe_wall_strike) <= 30 and spot > pe_wall_strike and atm_ce_vol > 5000
                        reject_ce_wall = abs(spot - ce_wall_strike) <= 30 and spot < ce_wall_strike and atm_pe_vol > 5000

                        if bounce_pe_wall:
                            if self.debouncer.edge("bounce_support", True):
                                self.logger.info(f"event=trade Bounce off Put Wall ({pe_wall_strike}). Volume Surge CE. Buying CE {atm_ce_sym} at {atm_ce_ltp:.2f}")

                                try:
                                    resp = self.api_client.placesmartorder(
                                        strategy=self.strategy_name,
                                        symbol=atm_ce_sym,
                                        action="BUY",
                                        exchange=self.options_exchange,
                                        pricetype="MARKET",
                                        product=self.product,
                                        quantity=self.quantity,
                                        position_size=self.quantity
                                    )
                                    self.logger.info(f"Trade response: {resp}")

                                    self.limiter.record()
                                    self.wall_breach_sl_price = pe_wall_strike - 10 # Buffer

                                    resolved_leg = {
                                        "symbol": atm_ce_sym,
                                        "option_type": "CE",
                                        "action": "BUY",
                                        "quantity": self.quantity,
                                        "entry_price": atm_ce_ltp
                                    }

                                    self.all_open_legs.append(resolved_leg)
                                    self.tracker.add_legs([resolved_leg], [atm_ce_ltp], side="BUY")
                                except Exception as e:
                                    self.logger.error(f"Failed to place order: {e}")

                        elif reject_ce_wall:
                            if self.debouncer.edge("reject_resistance", True):
                                self.logger.info(f"event=trade Rejection from Call Wall ({ce_wall_strike}). Volume Surge PE. Buying PE {atm_pe_sym} at {atm_pe_ltp:.2f}")

                                try:
                                    resp = self.api_client.placesmartorder(
                                        strategy=self.strategy_name,
                                        symbol=atm_pe_sym,
                                        action="BUY",
                                        exchange=self.options_exchange,
                                        pricetype="MARKET",
                                        product=self.product,
                                        quantity=self.quantity,
                                        position_size=self.quantity
                                    )
                                    self.logger.info(f"Trade response: {resp}")

                                    self.limiter.record()
                                    self.wall_breach_sl_price = ce_wall_strike + 10 # Buffer

                                    resolved_leg = {
                                        "symbol": atm_pe_sym,
                                        "option_type": "PE",
                                        "action": "BUY",
                                        "quantity": self.quantity,
                                        "entry_price": atm_pe_ltp
                                    }

                                    self.all_open_legs.append(resolved_leg)
                                    self.tracker.add_legs([resolved_leg], [atm_pe_ltp], side="BUY")
                                except Exception as e:
                                    self.logger.error(f"Failed to place order: {e}")

            except Exception as e:
                self.logger.error(f"Main loop error: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyOIWallStrategy().run()
