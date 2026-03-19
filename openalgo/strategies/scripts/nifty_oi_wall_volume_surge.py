#!/usr/bin/env python3
"""
Nifty OI Wall + Volume Surge Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Identifies OI walls and enters on bounce/rejection confirmed by volume surge.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

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

logger = PrintLogger()

# API Key retrieval (MANDATORY)
API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

if not API_KEY:
    try:
        from database.auth_db import get_first_available_api_key
        API_KEY = get_first_available_api_key()
        if API_KEY:
            logger.info("Successfully retrieved API Key from database.")
    except Exception as e:
        logger.warning(f"Warning: Could not retrieve API key from database: {e}")

if not API_KEY:
    raise ValueError("API Key must be set in OPENALGO_APIKEY environment variable")


# Configuration Section
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyOIWallVolumeSurge")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Risk management
SL_PCT = safe_float(os.getenv("SL_PCT", "30.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "60.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "20"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "5"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

# Strategy specific parameters
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "15"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

VOLUME_SURGE_THRESHOLD = safe_int(os.getenv("VOLUME_SURGE_THRESHOLD", "5000"))
DISTANCE_FROM_WALL = safe_float(os.getenv("DISTANCE_FROM_WALL", "25.0"))
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:30")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")

class NiftyOIWallVolumeSurge:
    def __init__(self):
        self.logger = logger
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Track position
        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )

        self.expiry = None
        self.last_expiry_check = 0
        self.last_volumes = {}

        # Track dynamic SL based on wall breach
        self.wall_strike_sl = None

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")
        self.logger.info(format_kv(
            underlying=UNDERLYING,
            vol_thresh=VOLUME_SURGE_THRESHOLD,
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold=MAX_HOLD_MIN
        ))

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

    def get_oi_walls(self, chain):
        max_ce_oi = 0
        ce_wall_strike = None
        max_pe_oi = 0
        pe_wall_strike = None

        for item in chain:
            strike = item.get("strike", 0)
            ce_oi = safe_int(item.get("ce", {}).get("oi", 0))
            pe_oi = safe_int(item.get("pe", {}).get("oi", 0))

            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                ce_wall_strike = strike

            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                pe_wall_strike = strike

        return ce_wall_strike, max_ce_oi, pe_wall_strike, max_pe_oi

    def check_volume_surge(self, chain, strike, option_type):
        for item in chain:
            if item.get("strike") == strike:
                opt = item.get(option_type.lower(), {})
                symbol = opt.get("symbol")
                current_vol = safe_int(opt.get("volume", 0))

                if not symbol:
                    return False, 0

                last_vol = self.last_volumes.get(symbol, current_vol)
                self.last_volumes[symbol] = current_vol

                vol_diff = current_vol - last_vol
                return vol_diff > VOLUME_SURGE_THRESHOLD, vol_diff

        return False, 0

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
            self.wall_strike_sl = None
            return

        exit_orders.sort(key=lambda x: 0 if x['action'] == 'BUY' else 1)

        for order in exit_orders:
            try:
                # Need to use APIClient for placesmartorder single leg
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
        self.wall_strike_sl = None
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
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))
                if underlying_ltp == 0:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # Get OI Walls
                ce_wall, ce_max_oi, pe_wall, pe_max_oi = self.get_oi_walls(chain)

                # Check dynamic wall stop-loss before standard exits
                dynamic_sl_hit = False
                if self.tracker.open_legs and self.wall_strike_sl is not None:
                    # If we bought CE off PE support, SL is if underlying drops below PE wall
                    if self.tracker.side == "BUY" and self.tracker.open_legs[0].get("option_type") == "CE":
                        if underlying_ltp < self.wall_strike_sl:
                            dynamic_sl_hit = True

                    # If we bought PE off CE resistance, SL is if underlying rises above CE wall
                    elif self.tracker.side == "BUY" and self.tracker.open_legs[0].get("option_type") == "PE":
                        if underlying_ltp > self.wall_strike_sl:
                            dynamic_sl_hit = True

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if dynamic_sl_hit:
                        self._close_position(chain, f"dynamic_sl_wall_breach ({self.wall_strike_sl})")
                        time.sleep(SLEEP_SECONDS)
                        continue
                    elif exit_now or self.should_terminate():
                        reason = exit_reason if exit_now else "EOD Auto-Squareoff"
                        self._close_position(chain, reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.is_entry_window_open() and not self.should_terminate():

                    buy_ce_signal = False
                    buy_pe_signal = False
                    reason = ""
                    wall_sl = None
                    atm_item = next((item for item in chain if item.get("ce", {}).get("label") == "ATM"), None)

                    if ce_wall and pe_wall and atm_item:
                        # Bounce off PE wall (Support)
                        dist_to_pe_wall = underlying_ltp - pe_wall
                        if 0 < dist_to_pe_wall <= DISTANCE_FROM_WALL:
                            is_surge, vol_diff = self.check_volume_surge(chain, pe_wall, "PE")
                            if is_surge:
                                buy_ce_signal = True
                                reason = f"bounce_off_pe_wall_{pe_wall}_vol_surge_{vol_diff}"
                                wall_sl = pe_wall # Support breached

                        # Rejection from CE wall (Resistance)
                        dist_to_ce_wall = ce_wall - underlying_ltp
                        if 0 < dist_to_ce_wall <= DISTANCE_FROM_WALL:
                            is_surge, vol_diff = self.check_volume_surge(chain, ce_wall, "CE")
                            if is_surge:
                                buy_pe_signal = True
                                reason = f"reject_from_ce_wall_{ce_wall}_vol_surge_{vol_diff}"
                                wall_sl = ce_wall # Resistance breached

                        # Debounce and evaluate signal
                        signal_triggered = buy_ce_signal or buy_pe_signal
                        if self.debouncer.edge("entry_signal", signal_triggered):
                            if self.limiter.allow():
                                option_type = "CE" if buy_ce_signal else "PE"
                                opt_data = atm_item.get(option_type.lower(), {})
                                symbol = opt_data.get("symbol")
                                ltp = safe_float(opt_data.get("ltp"))

                                if symbol and ltp > 0:
                                    self.logger.info(f"Entry Signal! {reason}. Buying {option_type}...")

                                    try:
                                        # Place single leg smart order
                                        res = self.api_client.placesmartorder(
                                            strategy=STRATEGY_NAME,
                                            symbol=symbol,
                                            action="BUY",
                                            exchange=OPTIONS_EXCHANGE,
                                            pricetype="MARKET",
                                            product=PRODUCT,
                                            quantity=QUANTITY,
                                            position_size=QUANTITY
                                        )

                                        if res.get("status") == "success":
                                            self.logger.info(f"Entry Order Success: {res}")
                                            self.limiter.record()

                                            leg_info = {
                                                "symbol": symbol,
                                                "option_type": option_type,
                                                "action": "BUY",
                                                "quantity": QUANTITY,
                                                "product": PRODUCT,
                                                "entry_price": ltp
                                            }

                                            self.tracker.add_legs(
                                                legs=[leg_info],
                                                entry_prices=[ltp],
                                                side="BUY"
                                            )
                                            self.wall_strike_sl = wall_sl
                                            self.logger.info(f"Position tracked. Dynamic SL at {self.wall_strike_sl}")
                                        else:
                                            self.logger.error(f"Entry Order Failed: {res.get('message')}")

                                    except Exception as e:
                                        self.logger.error(f"Order Execution Error: {e}")

                # Update volume caches for next check if no action taken
                if chain:
                    for item in chain:
                        if item.get("ce", {}).get("symbol"):
                            self.last_volumes[item["ce"]["symbol"]] = safe_int(item["ce"].get("volume", 0))
                        if item.get("pe", {}).get("symbol"):
                            self.last_volumes[item["pe"]["symbol"]] = safe_int(item["pe"].get("volume", 0))

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    try:
        strategy = NiftyOIWallVolumeSurge()
        strategy.run()
    except KeyboardInterrupt:
        print("Strategy stopped by user.")
    except Exception as e:
        print(f"Critical Error: {e}")
        sys.exit(1)
