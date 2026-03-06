#!/usr/bin/env python3
"""
Nifty Iron Condor Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if straddle premium > 120. Sells OTM2, buys OTM4.
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

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "NIFTY_IRON_CONDOR")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        # Risk Parameters
        self.sl_pct = safe_float(os.getenv("SL_PCT", "40"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        # Entry Parameters
        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120"), 120.0)

        # Loop Parameters
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "30"), 30)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "300"), 300)
        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "180"), 180)
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        # Clients and State
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
        self.last_trade_date = None

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if isinstance(res, dict) and res.get("status") == "success" and "data" in res:
                    dates = res["data"]
                    if dates:
                        self.expiry = choose_nearest_expiry(dates)
                        self.last_expiry_refresh = now
                        self.logger.info(format_kv(event="expiry_updated", expiry=self.expiry))
                    else:
                        self.logger.warning("No expiry dates returned.")
                else:
                    self.logger.warning(f"Failed to fetch expiry: {res}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def reset_daily_state_if_needed(self):
        current_date = datetime.now().date()
        if self.last_trade_date != current_date:
            self.entered_today = False
            self.last_trade_date = current_date
            self.limiter.reset()

    def can_trade(self) -> bool:
        now = datetime.now()

        # Check if already entered today
        if self.entered_today:
            return False

        # Entry time checks: After 10:00 AM, before 3:15 PM
        current_time = now.time()
        start_time = datetime.strptime("10:00:00", "%H:%M:%S").time()
        end_time = datetime.strptime("15:15:00", "%H:%M:%S").time()

        if not (start_time <= current_time <= end_time):
            return False

        return self.limiter.allow()

    def _close_position(self, chain: list, reason: str):
        if not self.tracker.open_legs:
            return

        self.logger.info(format_kv(event="exit_signal", reason=reason, time=datetime.now().strftime("%H:%M:%S")))

        # Reverse the legs to close the position
        close_legs = []
        for leg in self.tracker.open_legs:
            # Swap BUY to SELL, SELL to BUY
            close_action = "BUY" if leg.get("action") == "SELL" else "SELL"
            close_legs.append({
                "offset": leg.get("offset"),
                "option_type": leg.get("option_type"),
                "action": close_action,
                "quantity": leg.get("quantity"),
                "product": leg.get("product", self.product)
            })

        # Optimization: Place BUY legs before SELL legs
        close_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            response = self.client.optionsmultiorder(
                strategy=f"{self.strategy_name}_EXIT",
                underlying=self.underlying,
                exchange=self.underlying_exchange, # NFO uses NSE_INDEX for underlying
                expiry_date=self.expiry,
                legs=close_legs
            )
            self.logger.info(format_kv(event="trade", type="exit", response=str(response)))
            self.tracker.clear()
        except Exception as e:
            self.logger.error(f"Failed to execute exit order: {e}")

    def force_eod_exit(self, chain: list):
        now = datetime.now().time()
        eod_time = datetime.strptime("15:15:00", "%H:%M:%S").time()

        if now >= eod_time and self.tracker.open_legs:
            self._close_position(chain, "eod_squareoff")

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} Strategy...")
        self.logger.info(f"Config: SL={self.sl_pct}% TP={self.tp_pct}% MaxHold={self.max_hold_min}m Premium>={self.min_straddle_premium}")

        while True:
            try:
                self.reset_daily_state_if_needed()

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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)
                atm_strike = chain_resp.get("atm_strike", 0.0)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                    self.force_eod_exit(chain)
                    time.sleep(self.sleep_seconds)
                    continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    # Find ATM premium
                    atm_ce_ltp = 0.0
                    atm_pe_ltp = 0.0

                    for item in chain:
                        if item.get("strike") == atm_strike:
                            atm_ce_ltp = item.get("ce", {}).get("ltp", 0.0)
                            atm_pe_ltp = item.get("pe", {}).get("ltp", 0.0)
                            break

                    straddle_premium = atm_ce_ltp + atm_pe_ltp

                    self.logger.debug(format_kv(spot=spot, atm=atm_strike, straddle=straddle_premium))

                    # Signal: Straddle premium > threshold
                    signal = straddle_premium > self.min_straddle_premium

                    # Debounce to prevent multiple rapid attempts
                    if self.debouncer.edge("entry_signal", signal):
                        self.logger.info(format_kv(
                            event="entry_signal",
                            spot=spot,
                            straddle=straddle_premium,
                            threshold=self.min_straddle_premium
                        ))

                        # Define Iron Condor Legs
                        # Buy wings first for margin benefit
                        legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        # Determine entry prices for tracker
                        # In a real scenario, this would come from order response.
                        # We approximate with current LTP from chain
                        entry_prices = []
                        for leg in legs:
                            offset = leg["offset"]
                            otype = leg["option_type"].lower()
                            # Search chain for this offset
                            ltp = 0.0
                            for item in chain:
                                if item.get(otype, {}).get("label") == offset:
                                    ltp = item.get(otype, {}).get("ltp", 0.0)
                                    break
                            entry_prices.append(ltp)

                        # Place order
                        try:
                            response = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.underlying_exchange,
                                expiry_date=self.expiry,
                                legs=legs
                            )
                            self.logger.info(format_kv(event="trade", type="entry", response=str(response)))

                            self.limiter.record()
                            self.entered_today = True

                            # Track all legs so they are all closed on exit
                            # The OptionPositionTracker side="SELL" argument tells it to track
                            # SL/TP based on the performance of the SELL legs in the position
                            self.tracker.add_legs(legs, entry_prices, side="SELL")

                        except Exception as e:
                            self.logger.error(f"Failed to execute entry order: {e}")

            except Exception as e:
                self.logger.error(f"Main loop error: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
