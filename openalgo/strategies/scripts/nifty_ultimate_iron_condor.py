#!/usr/bin/env python3
"""
NIFTY Ultimate Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy targeting 10 AM entry if straddle premium > 120, selling OTM2 and buying OTM4.
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
        safe_int
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

class StrategyConfig:
    STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NIFTY_ULTIMATE_IC")
    UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
    UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
    OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
    PRODUCT = os.getenv("PRODUCT", "MIS")
    QUANTITY = int(os.getenv("QUANTITY", "1"))
    STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "12"))
    SL_PCT = float(os.getenv("SL_PCT", "40.0"))
    TP_PCT = float(os.getenv("TP_PCT", "50.0"))
    MAX_HOLD_MIN = float(os.getenv("MAX_HOLD_MIN", "45.0"))
    COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))
    SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
    EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
    MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
    MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))
    EXPIRY_DATE = os.getenv("EXPIRY_DATE", "")
    MIN_STRADDLE_PREM = float(os.getenv("MIN_STRADDLE_PREM", "120.0"))

class NiftyUltimateIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.cfg = StrategyConfig()

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.cfg.SL_PCT, tp_pct=self.cfg.TP_PCT, max_hold_min=self.cfg.MAX_HOLD_MIN)
        self.limiter = TradeLimiter(max_per_day=self.cfg.MAX_ORDERS_PER_DAY, max_per_hour=self.cfg.MAX_ORDERS_PER_HOUR, cooldown_seconds=self.cfg.COOLDOWN_SECONDS)
        self.debouncer = SignalDebouncer()

        self.expiry = normalize_expiry(self.cfg.EXPIRY_DATE)
        self.last_expiry_refresh = 0
        self.all_open_legs = []
        self.entered_today = False
        self.reset_date = datetime.now().date()

        self.logger.info(format_kv(event="init", strategy=self.cfg.STRATEGY_NAME, underlying=self.cfg.UNDERLYING))

    def _check_reset_daily(self):
        now_date = datetime.now().date()
        if now_date != self.reset_date:
            self.entered_today = False
            self.reset_date = now_date
            self.all_open_legs = []
            self.tracker.clear()
            self.logger.info(format_kv(event="daily_reset"))

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.cfg.EXPIRY_REFRESH_SEC):
            res = self.client.expiry(self.cfg.UNDERLYING, self.cfg.OPTIONS_EXCHANGE, "options")
            if res and res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest and nearest != self.expiry:
                    self.expiry = nearest
                    self.logger.info(format_kv(event="expiry_updated", expiry=self.expiry))
            self.last_expiry_refresh = now

    def can_trade_now(self):
        now = datetime.now().time()
        # Ensure it's between 10 AM and 2:30 PM
        start_time = datetime.strptime("10:00", "%H:%M").time()
        end_time = datetime.strptime("14:30", "%H:%M").time()
        return start_time <= now <= end_time

    def is_eod_squareoff(self):
        now = datetime.now().time()
        sq_time = datetime.strptime("15:15", "%H:%M").time()
        return now >= sq_time

    def _close_position(self, chain, reason):
        if not self.all_open_legs:
            return

        self.logger.info(format_kv(event="trade", action="CLOSE", reason=reason, legs=len(self.all_open_legs)))

        for leg in self.all_open_legs:
            sym = leg.get("symbol")
            if not sym:
                continue
            orig_action = leg.get("action", "BUY")
            close_action = "BUY" if orig_action == "SELL" else "SELL"

            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.cfg.STRATEGY_NAME,
                    symbol=sym,
                    action=close_action,
                    exchange=self.cfg.OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=self.cfg.PRODUCT,
                    quantity=leg.get("quantity", self.cfg.QUANTITY),
                    position_size=0
                )
                self.logger.info(format_kv(event="trade", leg=sym, action=close_action, status=resp.get("status")))
            except Exception as e:
                self.logger.error(format_kv(event="trade_error", leg=sym, error=str(e)))

        self.tracker.clear()
        self.all_open_legs = []

    def _execute_entry(self, chain, atm_strike):
        # We need to construct the legs, OTM2 SELL, OTM4 BUY
        # Note: In client.optionsmultiorder we can use offsets like 'OTM2', but OptionPositionTracker needs symbols and entry prices
        # We can extract the required symbols directly from the chain to place individual orders or use multiorder and map it.
        # But wait, optionchain response doesn't give us the executed price of multiorder.
        # It's better to use multiorder and assume execution at LTP for tracker, or read the response if it provides prices.

        legs = [
            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.cfg.QUANTITY, "product": self.cfg.PRODUCT},
            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.cfg.QUANTITY, "product": self.cfg.PRODUCT},
            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.cfg.QUANTITY, "product": self.cfg.PRODUCT},
            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.cfg.QUANTITY, "product": self.cfg.PRODUCT},
        ]

        self.logger.info(format_kv(event="trade", action="ENTRY", message="Placing multi-leg order"))

        resp = self.client.optionsmultiorder(
            strategy=self.cfg.STRATEGY_NAME,
            underlying=self.cfg.UNDERLYING,
            exchange=self.cfg.UNDERLYING_EXCHANGE,
            expiry_date=self.expiry,
            legs=legs
        )

        if resp.get("status") == "success":
            # Map chain to find LTPs for tracker
            # We need to know which strikes are OTM2, OTM4
            # A simple way is to find labels 'OTM2', 'OTM4'

            executed_legs = []
            short_legs = []
            short_entry_prices = []

            for leg_req in legs:
                offset = leg_req["offset"]
                opt_type = leg_req["option_type"].lower()
                action = leg_req["action"]

                # Find matching option in chain
                for item in chain:
                    opt_data = item.get(opt_type, {})
                    if opt_data.get("label") == offset:
                        sym = opt_data.get("symbol")
                        ltp = safe_float(opt_data.get("ltp"))
                        leg_info = {
                            "symbol": sym,
                            "action": action,
                            "quantity": leg_req["quantity"],
                            "entry_price": ltp
                        }
                        executed_legs.append(leg_info)

                        if action == "SELL":
                            short_legs.append(leg_info)
                            short_entry_prices.append(ltp)
                        break

            if executed_legs:
                self.all_open_legs = executed_legs
                self.tracker.add_legs(short_legs, short_entry_prices, side="SELL")
                self.entered_today = True
                self.limiter.record()
                self.logger.info(format_kv(event="trade_success", short_legs=len(short_legs), total_legs=len(executed_legs)))
            else:
                self.logger.warning(format_kv(event="trade_warning", message="Order succeeded but could not map chain symbols"))
        else:
            self.logger.error(format_kv(event="trade_failed", response=str(resp)))

    def get_atm_strike(self, chain):
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return item.get("strike")
        return None

    def calculate_straddle_premium(self, chain, atm_strike):
        ce_ltp = 0.0
        pe_ltp = 0.0
        for item in chain:
            if item.get("strike") == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0.0))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0.0))
                break
        return ce_ltp + pe_ltp

    def run(self):
        self.logger.info(format_kv(event="start", message="Strategy main loop started"))
        while True:
            try:
                self._check_reset_daily()

                if not is_market_open():
                    time.sleep(self.cfg.SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.cfg.SLEEP_SECONDS)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.cfg.UNDERLYING,
                    exchange=self.cfg.UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=self.cfg.STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.debug(format_kv(event="invalid_chain", reason=reason))
                    time.sleep(self.cfg.SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")
                if not atm_strike:
                    atm_strike = self.get_atm_strike(chain)

                # EXIT MANAGEMENT FIRST
                if self.all_open_legs:
                    if self.is_eod_squareoff():
                        self._close_position(chain, "eod_squareoff")
                        time.sleep(self.cfg.SLEEP_SECONDS)
                        continue

                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.cfg.SLEEP_SECONDS)
                        continue

                # ENTRY LOGIC
                if not self.all_open_legs and not self.entered_today and self.can_trade_now():
                    straddle_prem = self.calculate_straddle_premium(chain, atm_strike)
                    self.logger.debug(format_kv(event="eval", atm=atm_strike, straddle=straddle_prem))

                    if straddle_prem > self.cfg.MIN_STRADDLE_PREM:
                        if self.limiter.allow():
                            self._execute_entry(chain, atm_strike)
                        else:
                            self.logger.debug(format_kv(event="rate_limit", message="Trade limited by TradeLimiter"))

            except Exception as e:
                self.logger.error(format_kv(event="loop_error", error=str(e)))

            time.sleep(self.cfg.SLEEP_SECONDS)

if __name__ == "__main__":
    NiftyUltimateIronCondor().run()
