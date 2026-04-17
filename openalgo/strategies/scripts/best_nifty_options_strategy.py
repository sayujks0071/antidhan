#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if ATM straddle > 120. Sells OTM2, Buys OTM4.
"""
import os
import sys
import time
from datetime import datetime, timezone, timedelta

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

# Module constants
IST = timezone(timedelta(hours=5, minutes=30))

def get_atm_strike(chain):
    for item in chain:
        if item.get("ce", {}).get("label") == "ATM":
            return float(item["strike"])
    return None

def calculate_straddle_premium(chain, atm_strike):
    for item in chain:
        if float(item["strike"]) == atm_strike:
            ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0.0))
            pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0.0))
            return ce_ltp + pe_ltp
    return 0.0

class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_IronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE", "120"))

        self.cooldown_sec = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_sec = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # Tools
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_day,
            max_per_hour=self.max_orders_hour,
            cooldown_seconds=self.cooldown_sec
        )
        self.debouncer = SignalDebouncer()

        # State
        self.expiry = None
        self.last_expiry_refresh = 0

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    self.expiry = choose_nearest_expiry(res["data"])
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry: {e}")

    def _close_position(self, chain, reason):
        self.logger.info(f"event=trade Closing position. Reason: {reason}")

        # Sort legs to prioritize closing shorts (BUY) before closing longs (SELL)
        sorted_legs = sorted(self.tracker.open_legs, key=lambda leg: 0 if leg["action"] == "SELL" else 1)

        for leg in sorted_legs:
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            try:
                self.client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0
                )
                self.logger.info(f"event=trade action={close_action} symbol={leg['symbol']}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()

    def check_time_filters(self):
        now_ist = datetime.now(IST)

        # 10:00 AM to 3:15 PM
        start_time = now_ist.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = now_ist.replace(hour=15, minute=15, second=0, microsecond=0)
        eod_time = now_ist.replace(hour=15, minute=15, second=0, microsecond=0)

        can_trade = start_time <= now_ist < end_time
        eod_square_off = now_ist >= eod_time

        return can_trade, eod_square_off

    def run(self):
        self.logger.info(f"Starting {self.strategy_name}")

        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_sec)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_sec)
                    continue

                can_trade, eod_square_off = self.check_time_filters()

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, valid_reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {valid_reason}")
                    time.sleep(self.sleep_sec)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    if eod_square_off:
                        self._close_position(chain, "EOD_Square_Off")
                    else:
                        exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                        if exit_now:
                            self._close_position(chain, exit_reason)

                # Avoid entering after EOD
                if not can_trade:
                    time.sleep(self.sleep_sec)
                    continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.limiter.allow():
                    atm_strike = get_atm_strike(chain)
                    if not atm_strike:
                        time.sleep(self.sleep_sec)
                        continue

                    premium = calculate_straddle_premium(chain, atm_strike)

                    self.logger.info(format_kv(
                        spot=chain_resp.get("underlying_ltp"),
                        atm=atm_strike,
                        straddle=f"{premium:.1f}"
                    ))

                    signal_condition = premium > self.min_straddle_premium

                    if self.debouncer.edge("entry_signal", signal_condition):
                        self.logger.info(f"event=trade Signal detected. Premium: {premium}")

                        # Prioritize BUY legs before SELL for margin efficiency
                        multi_legs = [
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
                                legs=multi_legs
                            )

                            self.logger.info(f"event=trade Trade response: {resp}")

                            # Find actual leg prices and symbols from chain
                            tracked_legs = []
                            entry_prices = []

                            for l in multi_legs:
                                # Need to find the symbol with this offset
                                for item in chain:
                                    opt_data = item.get(l["option_type"].lower(), {})
                                    if opt_data.get("label") == l["offset"]:
                                        tracked_legs.append({
                                            "symbol": opt_data["symbol"],
                                            "action": l["action"],
                                            "quantity": l["quantity"]
                                        })
                                        entry_prices.append(safe_float(opt_data.get("ltp")))
                                        break

                            if len(tracked_legs) == 4:
                                self.tracker.add_legs(tracked_legs, entry_prices, side="SELL")
                                self.limiter.record()
                                self.logger.info(f"Position opened with 4 legs")
                            else:
                                self.logger.error("Could not find all legs in chain for tracking")

                        except Exception as e:
                            self.logger.error(f"Error placing order: {e}")

            except Exception as e:
                self.logger.error(f"Main loop error: {e}")

            time.sleep(self.sleep_sec)

if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
