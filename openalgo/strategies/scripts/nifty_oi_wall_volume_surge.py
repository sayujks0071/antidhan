#!/usr/bin/env python3
"""
Nifty OI Wall + Volume Surge - NIFTY Options (OpenAlgo Web UI Compatible)
Identifies Call and Put OI walls and triggers trades on bounces/rejections confirmed by volume surges (>5000), using a dynamic stop-loss on wall breaches.
CHANGELOG:
- 2024-05-20: Initial version with enterprise risk management
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

# Configuration Section
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyOIWallVolumeSurge")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

SL_PCT = safe_float(os.getenv("SL_PCT", "30.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "60.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "20"))

COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "5"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:30")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:45")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")
VOLUME_SURGE_THRESHOLD = safe_int(os.getenv("VOLUME_SURGE_THRESHOLD", "5000"))

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

        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_check = 0

        # State tracking for dynamic exit
        self.current_wall_strike = None
        self.wall_type = None # 'SUPPORT' or 'RESISTANCE'

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > EXPIRY_REFRESH_SEC):
            try:
                res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
                if res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        self.expiry = choose_nearest_expiry(dates)
                        self.last_expiry_check = now
                        self.logger.info(f"Selected Expiry: {self.expiry}")
                    else:
                        self.logger.warning("No expiry dates found.")
                else:
                    self.logger.warning(f"Expiry fetch failed: {res.get('message')}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def is_entry_window_open(self):
        now = datetime.now().time()
        try:
            start = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
            end = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()
            return start <= now <= end
        except ValueError:
            return False

    def should_terminate(self):
        now = datetime.now().time()
        try:
            exit_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
            return now >= exit_time
        except ValueError:
            return False

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position. Reason: {reason}")
        exit_orders = []
        for leg in self.tracker.open_legs:
            close_action = "BUY" if leg.get("action") == "SELL" else "SELL"
            exit_orders.append({
                "symbol": leg["symbol"],
                "action": close_action,
                "quantity": leg["quantity"],
                "product": PRODUCT,
                "pricetype": "MARKET"
            })

        if not exit_orders:
            self.tracker.clear()
            return

        exit_orders.sort(key=lambda x: 0 if x['action'] == 'BUY' else 1)

        for order in exit_orders:
            try:
                res = self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=order["symbol"],
                    action=order["action"],
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=order["product"],
                    quantity=order["quantity"],
                    position_size=0
                )
                self.logger.info(f"Exit Order: {order['symbol']} {order['action']} -> {res}")
            except Exception as e:
                self.logger.error(f"Exit failed for {order['symbol']}: {e}")

        self.tracker.clear()
        self.current_wall_strike = None
        self.wall_type = None
        self.logger.info("Position closed and tracker cleared.")

    def run(self):
        self.logger.info("Starting Strategy Loop...")

        while True:
            try:
                if not is_market_open():
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])

                spot_price = chain_resp.get("underlying_ltp", 0)
                if spot_price == 0:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # Dynamic SL on wall breach
                    if not exit_now and self.current_wall_strike is not None:
                        if self.wall_type == "SUPPORT" and spot_price < self.current_wall_strike:
                            exit_now = True
                            exit_reason = "Support Wall Breached"
                        elif self.wall_type == "RESISTANCE" and spot_price > self.current_wall_strike:
                            exit_now = True
                            exit_reason = "Resistance Wall Breached"

                    if exit_now or self.should_terminate():
                        reason = exit_reason if exit_now else "EOD Auto-Squareoff"
                        self._close_position(chain, reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.is_entry_window_open() and not self.should_terminate():
                    max_ce_oi = 0
                    max_ce_strike = 0
                    max_pe_oi = 0
                    max_pe_strike = 0

                    for item in chain:
                        ce_oi = safe_float(item.get("ce", {}).get("oi", 0))
                        pe_oi = safe_float(item.get("pe", {}).get("oi", 0))
                        strike = float(item["strike"])

                        if ce_oi > max_ce_oi:
                            max_ce_oi = ce_oi
                            max_ce_strike = strike
                        if pe_oi > max_pe_oi:
                            max_pe_oi = pe_oi
                            max_pe_strike = strike

                    # Check proximity and volume surge
                    bounce_signal = False
                    reject_signal = False

                    atm_ce = None
                    atm_pe = None
                    for item in chain:
                        if item.get("ce", {}).get("label") == "ATM":
                            atm_ce = item.get("ce", {})
                            atm_pe = item.get("pe", {})
                            break

                    if atm_ce and atm_pe:
                        # Bounce off Put OI Wall (Support)
                        if abs(spot_price - max_pe_strike) <= 30:
                            if safe_float(atm_pe.get("volume", 0)) > VOLUME_SURGE_THRESHOLD:
                                bounce_signal = True

                        # Rejection from Call OI Wall (Resistance)
                        if abs(spot_price - max_ce_strike) <= 30:
                            if safe_float(atm_ce.get("volume", 0)) > VOLUME_SURGE_THRESHOLD:
                                reject_signal = True

                    signal_active = bounce_signal or reject_signal

                    if self.debouncer.edge("WALL_BOUNCE", signal_active):
                        if not self.limiter.allow():
                            self.logger.info("Trade limit reached.")
                        else:
                            leg_to_buy = None
                            if bounce_signal:
                                leg_to_buy = {
                                    "symbol": atm_ce.get("symbol"),
                                    "action": "BUY",
                                    "quantity": QUANTITY,
                                    "product": PRODUCT,
                                    "ltp": safe_float(atm_ce.get("ltp", 0))
                                }
                                self.current_wall_strike = max_pe_strike
                                self.wall_type = "SUPPORT"
                            else:
                                leg_to_buy = {
                                    "symbol": atm_pe.get("symbol"),
                                    "action": "BUY",
                                    "quantity": QUANTITY,
                                    "product": PRODUCT,
                                    "ltp": safe_float(atm_pe.get("ltp", 0))
                                }
                                self.current_wall_strike = max_ce_strike
                                self.wall_type = "RESISTANCE"

                            if leg_to_buy and leg_to_buy["symbol"]:
                                try:
                                    response = self.api_client.placesmartorder(
                                        strategy=STRATEGY_NAME,
                                        symbol=leg_to_buy["symbol"],
                                        action=leg_to_buy["action"],
                                        exchange=OPTIONS_EXCHANGE,
                                        pricetype="MARKET",
                                        product=leg_to_buy["product"],
                                        quantity=leg_to_buy["quantity"],
                                        position_size=1
                                    )
                                    if response.get("status") == "success":
                                        self.logger.info(f"Order Success: {response}")
                                        self.limiter.record()

                                        tracking_legs = [leg_to_buy]
                                        entry_prices = [leg_to_buy["ltp"]]
                                        self.tracker.add_legs(legs=tracking_legs, entry_prices=entry_prices, side="BUY")
                                        self.logger.info("Position tracked.")
                                    else:
                                        self.logger.error(f"Order Failed: {response.get('message')}")
                                except Exception as e:
                                    self.logger.error(f"Order Execution Error: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    try:
        strategy = NiftyOIWallStrategy()
        strategy.run()
    except KeyboardInterrupt:
        print("Strategy stopped by user.")
    except Exception as e:
        print(f"Critical Error: {e}")
        sys.exit(1)
