#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM (if straddle > 120), sells OTM2 / buys OTM4, manages via 40% SL / 50% TP / 45m time stop.
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
        self.strategy_name = os.getenv("STRATEGY_NAME", "nifty_iron_condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        # Risk & Trade parameters
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"))
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = safe_float(os.getenv("SL_PCT", "40"))
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "30"))
        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "300"))

        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Clients & State
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
        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False

        self.logger.info(f"Initialized Nifty Iron Condor Strategy: SL={self.sl_pct}%, TP={self.tp_pct}%, MaxHold={self.max_hold_min}m")

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            try:
                manual_expiry = os.getenv("EXPIRY_DATE")
                if manual_expiry:
                    self.expiry = normalize_expiry(manual_expiry)
                    self.last_expiry_refresh = now
                    return

                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data", [])
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Selected Expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        now = datetime.now()
        # Ensure we are after 10:00 AM and before 3:15 PM (15:15)
        current_time = now.time()
        start_time = datetime.strptime("10:00", "%H:%M").time()
        end_time = datetime.strptime("15:15", "%H:%M").time()

        if not (start_time <= current_time <= end_time):
            return False

        if self.entered_today:
            return False

        if not self.limiter.allow():
            return False

        return True

    def find_leg(self, chain, offset, option_type):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset:
                return opt
        return None

    def _close_position(self, chain, reason):
        if not self.tracker.open_legs:
            return

        self.logger.info(f"event=trade Closing position. reason={reason}")
        close_legs = []
        for leg in self.tracker.open_legs:
            # Reverse action for closing
            close_action = "SELL" if leg["action"] == "BUY" else "BUY"
            close_legs.append({
                "offset": leg.get("offset"),
                "option_type": leg.get("option_type"),
                "action": close_action,
                "quantity": leg.get("quantity"),
                "product": leg.get("product")
            })

        # Optimization: Place BUY orders before SELL orders for margin benefit on exits too
        # But for Iron Condor exit, we are closing short positions (which means BUY) and closing long (SELL)
        # So BUY legs should come first.
        close_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            resp = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.underlying_exchange,
                expiry_date=self.expiry,
                legs=close_legs
            )
            self.logger.info(f"Trade response: {resp}")
            self.tracker.clear()
        except Exception as e:
            self.logger.error(f"Error closing position: {e}")

    def run(self):
        self.logger.info("Starting Nifty Iron Condor main loop.")
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")
                underlying_ltp = chain_resp.get("underlying_ltp")

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # Also check EOD square-off (3:15 PM)
                    now = datetime.now().time()
                    eod_time = datetime.strptime("15:15", "%H:%M").time()
                    if now >= eod_time:
                        exit_now = True
                        exit_reason = "eod_squareoff"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    atm_ce = self.find_leg(chain, "ATM", "CE")
                    atm_pe = self.find_leg(chain, "ATM", "PE")

                    if atm_ce and atm_pe:
                        straddle_premium = safe_float(atm_ce.get("ltp")) + safe_float(atm_pe.get("ltp"))
                        self.logger.debug(format_kv(spot=underlying_ltp, straddle=straddle_premium, min_required=self.min_straddle_premium))

                        signal_condition = straddle_premium > self.min_straddle_premium
                        signal = self.debouncer.edge("enter_ic", signal_condition)

                        if signal:
                            # Sell OTM2, Buy OTM4
                            sell_ce_opt = self.find_leg(chain, "OTM2", "CE")
                            sell_pe_opt = self.find_leg(chain, "OTM2", "PE")
                            buy_ce_opt = self.find_leg(chain, "OTM4", "CE")
                            buy_pe_opt = self.find_leg(chain, "OTM4", "PE")

                            if sell_ce_opt and sell_pe_opt and buy_ce_opt and buy_pe_opt:
                                self.logger.info(f"event=trade Entering Iron Condor. Straddle Premium: {straddle_premium}")

                                legs = [
                                    {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product, "symbol": buy_ce_opt.get("symbol")},
                                    {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product, "symbol": buy_pe_opt.get("symbol")},
                                    {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product, "symbol": sell_ce_opt.get("symbol")},
                                    {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product, "symbol": sell_pe_opt.get("symbol")},
                                ]

                                try:
                                    # Place the order via API
                                    resp = self.client.optionsmultiorder(
                                        strategy=self.strategy_name,
                                        underlying=self.underlying,
                                        exchange=self.underlying_exchange,
                                        expiry_date=self.expiry,
                                        legs=legs
                                    )
                                    self.logger.info(f"Trade response: {resp}")

                                    # Add position to tracker
                                    entry_prices = [
                                        buy_ce_opt.get("ltp"), buy_pe_opt.get("ltp"),
                                        sell_ce_opt.get("ltp"), sell_pe_opt.get("ltp")
                                    ]
                                    self.tracker.add_legs(legs, entry_prices, side="SELL")

                                    # Record the trade for limits
                                    self.limiter.record()
                                    self.entered_today = True

                                except Exception as e:
                                    self.logger.error(f"Error executing Iron Condor entry: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
