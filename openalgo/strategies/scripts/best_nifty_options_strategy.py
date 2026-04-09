#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor when straddle premium > 120, holds max 45m.
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
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

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
except ImportError as e:
    print(f"ERROR: Could not import strategy utilities: {e}", flush=True)
    sys.exit(1)

class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)

API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

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
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "best_nifty_iron_condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "10"))

        # Risk & Entry Parameters
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.min_premium = float(os.getenv("MIN_PREMIUM", "120.0"))

        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "20"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # Internal state
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

        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_check = 0

        self.logger.info(format_kv(
            event="init",
            strategy=self.strategy_name,
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold=self.max_hold_min
        ))

    def ensure_expiry(self):
        """Fetch or update the nearest expiry date."""
        if self.expiry and (time.time() - self.last_expiry_check < self.expiry_refresh_sec):
            return

        try:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res and res.get("status") == "success" and res.get("data"):
                expirations = res.get("data")
                self.expiry = choose_nearest_expiry(expirations)
                self.last_expiry_check = time.time()
                self.logger.info(format_kv(event="expiry_update", expiry=self.expiry))
            else:
                self.logger.warning(f"Failed to get expiry dates: {res}")
        except Exception as e:
            self.logger.error(f"Error fetching expiry: {e}")

    def _get_atm_strike_and_premium(self, chain):
        """Calculates ATM strike and total straddle premium."""
        straddle_premium = 0.0
        atm_strike = 0.0
        for item in chain:
            ce_label = item.get("ce", {}).get("label")
            if ce_label == "ATM":
                atm_strike = safe_float(item.get("strike"))
                straddle_premium += safe_float(item.get("ce", {}).get("ltp"))
                straddle_premium += safe_float(item.get("pe", {}).get("ltp"))
                break
        return atm_strike, straddle_premium

    def _get_leg_details(self, chain, offset, option_type):
        """Extracts symbol and ltp for a specific offset and option type."""
        for item in chain:
            opt_data = item.get(option_type.lower(), {})
            if opt_data.get("label") == offset:
                return opt_data.get("symbol"), safe_float(opt_data.get("ltp"))
        return None, 0.0

    def _close_position(self, chain, reason):
        """Closes all open legs."""
        self.logger.info(format_kv(event="exit_triggered", reason=reason))

        # Sort closing legs: BUY to cover shorts first, then SELL to close longs (Margin efficiency)
        close_orders = []
        for leg in self.tracker.open_legs:
            action = "BUY" if leg["action"] == "SELL" else "SELL"
            close_orders.append({
                "symbol": leg["symbol"],
                "action": action,
                "quantity": leg["quantity"]
            })

        close_orders.sort(key=lambda x: x["action"]) # BUY comes before SELL alphabetically

        for order in close_orders:
            try:
                self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=order["symbol"],
                    action=order["action"],
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=order["quantity"],
                    position_size=0
                )
                self.logger.info(format_kv(
                    event="trade",
                    msg="Leg closed",
                    symbol=order["symbol"],
                    action=order["action"]
                ))
            except Exception as e:
                self.logger.error(f"Error closing leg {order['symbol']}: {e}")

        self.tracker.clear()

    def run(self):
        self.logger.info("Strategy starting loop...")
        while True:
            try:
                # 1. Market Hours Check
                now = datetime.now()
                current_time = now.time()

                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                # 2. Expiry Management
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # 3. Fetch Data
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
                spot = safe_float(chain_resp.get("underlying_ltp"))

                # 4. EXIT MANAGEMENT
                if self.tracker.open_legs:
                    # Intraday Auto Square-off at 3:15 PM (15:15)
                    if current_time.hour == 15 and current_time.minute >= 15:
                        self._close_position(chain, "intraday_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # 5. ENTRY LOGIC
                # Only enter between 10:00 AM and 3:00 PM
                if current_time.hour < 10 or current_time.hour >= 15:
                    time.sleep(self.sleep_seconds)
                    continue

                atm_strike, straddle_prem = self._get_atm_strike_and_premium(chain)

                # We need premium > min_premium for entry
                entry_condition = straddle_prem > self.min_premium
                signal = self.debouncer.edge("iron_condor_entry", entry_condition)

                if not self.tracker.open_legs and signal:
                    if self.limiter.allow():
                        self.logger.info(format_kv(
                            event="signal",
                            spot=spot,
                            atm=atm_strike,
                            straddle_prem=straddle_prem
                        ))

                        # Define legs: BUY outer wings first, SELL inner wings
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

                            self.logger.info(format_kv(event="trade", msg="Multiorder placed", status=resp.get("status")))
                            self.limiter.record()

                            # Extract actual symbols and entry prices from current chain to track them
                            tracker_legs = []
                            entry_prices = []

                            for leg in multi_legs:
                                sym, ltp = self._get_leg_details(chain, leg["offset"], leg["option_type"])
                                if sym:
                                    tracker_legs.append({
                                        "symbol": sym,
                                        "action": leg["action"],
                                        "quantity": leg["quantity"],
                                        "option_type": leg["option_type"],
                                        "offset": leg["offset"]
                                    })
                                    entry_prices.append(ltp)

                            if len(tracker_legs) == 4:
                                # Iron condor is a net SELL strategy (credit spread)
                                self.tracker.add_legs(tracker_legs, entry_prices, side="SELL")
                                self.logger.info(format_kv(event="position_opened", legs_tracked=len(tracker_legs)))
                            else:
                                self.logger.warning(f"Could not map all leg symbols from chain for tracking.")

                        except Exception as e:
                            self.logger.error(f"Error placing multi-leg order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    strategy = NiftyIronCondorStrategy()
    strategy.run()
