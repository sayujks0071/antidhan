#!/usr/bin/env python3
"""
NIFTY OI Wall & Volume Surge - NIFTY Options (OpenAlgo Web UI Compatible)
Identifies the strike with maximum Call OI (resistance) and Put OI (support).
Enters when spot approaches a wall strike with increasing volume.
Buys CE if spot bounces off put OI wall (support).
Buys PE if spot rejects from call OI wall (resistance).
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


class NiftyOIWallVolumeSurge:
    def __init__(self):
        self.logger = PrintLogger()
        self.logger.info("Initializing Nifty OI Wall & Volume Surge Strategy")

        # Strategy Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "NIFTY_OI_WALL")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"))
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "20"))

        # Specific parameters
        self.min_volume_surge = safe_int(os.getenv("MIN_VOLUME_SURGE", "5000"))
        self.wall_proximity_points = safe_int(os.getenv("WALL_PROXIMITY_POINTS", "30"))
        self.sl_pct = safe_float(os.getenv("SL_PCT", "30.0"))
        self.tp_pct = safe_float(os.getenv("TP_PCT", "60.0"))
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "20"))

        # Timing parameters
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "20"))
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "5"))
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

        # Initialize clients & utilities
        self.chain_client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=60
        )
        self.debouncer = SignalDebouncer()

        # State variables
        self.expiry = None
        self.last_expiry_check = 0
        self.call_wall_strike = None
        self.put_wall_strike = None
        self.prev_volume = {}

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            try:
                res = self.chain_client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_check = now
                    self.logger.info(f"Resolved expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error resolving expiry: {e}")

    def close_all_positions(self, chain, reason="closing"):
        if not self.tracker.open_legs:
            return

        self.logger.info(f"Closing position. Reason: {reason}")

        for leg in self.tracker.open_legs:
            # Reverse action
            close_action = "SELL" if leg["action"] == "BUY" else "BUY"
            symbol = leg.get("symbol")
            if not symbol:
                continue

            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg["quantity"],
                    position_size=1
                )
                self.logger.info(f"Close order response for {symbol}: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {symbol}: {e}")

        self.tracker.clear()

    def find_walls(self, chain):
        max_call_oi = 0
        max_put_oi = 0
        call_strike = None
        put_strike = None

        for item in chain:
            strike = item.get("strike", 0)
            ce = item.get("ce", {})
            pe = item.get("pe", {})

            ce_oi = safe_int(ce.get("oi", 0))
            pe_oi = safe_int(pe.get("oi", 0))

            if ce_oi > max_call_oi:
                max_call_oi = ce_oi
                call_strike = strike

            if pe_oi > max_put_oi:
                max_put_oi = pe_oi
                put_strike = strike

        return call_strike, put_strike

    def get_option_by_label(self, chain, label, option_type):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == label:
                return opt
        return None

    def run(self):
        while True:
            try:
                # 1. Ensure market is open and it's within our trading window
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                now = datetime.now()
                # Trading window: 9:30 AM to 2:30 PM for entry, exit by 3:15 PM
                current_time = now.time()

                # Check for EOD square-off
                if current_time >= datetime.strptime("15:15", "%H:%M").time():
                    if self.tracker.open_legs:
                        self.close_all_positions([], reason="EOD_SQUARE_OFF")
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # 2. Fetch chain data
                chain_resp = self.chain_client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=True)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot_price = safe_float(chain_resp.get("underlying_ltp", 0))

                if spot_price == 0:
                    time.sleep(self.sleep_seconds)
                    continue

                # Update walls
                self.call_wall_strike, self.put_wall_strike = self.find_walls(chain)

                # Update volume tracking and find surges
                call_vol_surge = False
                put_vol_surge = False

                for item in chain:
                    strike = item.get("strike", 0)
                    ce = item.get("ce", {})
                    pe = item.get("pe", {})

                    ce_vol = safe_int(ce.get("volume", 0))
                    pe_vol = safe_int(pe.get("volume", 0))

                    prev_ce_vol = self.prev_volume.get(f"{strike}_CE", ce_vol)
                    prev_pe_vol = self.prev_volume.get(f"{strike}_PE", pe_vol)

                    ce_surge = ce_vol - prev_ce_vol
                    pe_surge = pe_vol - prev_pe_vol

                    if ce_surge > self.min_volume_surge and strike == self.call_wall_strike:
                        call_vol_surge = True

                    if pe_surge > self.min_volume_surge and strike == self.put_wall_strike:
                        put_vol_surge = True

                    self.prev_volume[f"{strike}_CE"] = ce_vol
                    self.prev_volume[f"{strike}_PE"] = pe_vol

                # Log current state
                self.logger.debug(format_kv(
                    spot=spot_price,
                    c_wall=self.call_wall_strike,
                    p_wall=self.put_wall_strike,
                    c_surge=call_vol_surge,
                    p_surge=put_vol_surge
                ))

                # 3. Handle Exits
                if self.tracker.open_legs:
                    # Check standard exits (SL, TP, Time)
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # Dynamic SL based on wall breach
                    if not exit_now and self.tracker.side == "BUY":
                        for leg in self.tracker.open_legs:
                            # If we bought PE (rejected from call wall), exit if call wall breached (spot > call wall)
                            if "PE" in leg.get("symbol", "") and self.call_wall_strike and spot_price > self.call_wall_strike + 10:
                                exit_now = True
                                exit_reason = "call_wall_breach"
                                break
                            # If we bought CE (bounced from put wall), exit if put wall breached (spot < put wall)
                            if "CE" in leg.get("symbol", "") and self.put_wall_strike and spot_price < self.put_wall_strike - 10:
                                exit_now = True
                                exit_reason = "put_wall_breach"
                                break

                    if exit_now:
                        self.close_all_positions(chain, reason=exit_reason)

                    time.sleep(self.sleep_seconds)
                    continue

                # 4. Handle Entries (only between 9:30 AM and 2:30 PM)
                if current_time >= datetime.strptime("09:30", "%H:%M").time() and current_time <= datetime.strptime("14:30", "%H:%M").time():

                    buy_ce_cond = (
                        self.put_wall_strike is not None and
                        abs(spot_price - self.put_wall_strike) <= self.wall_proximity_points and
                        put_vol_surge
                    )

                    buy_pe_cond = (
                        self.call_wall_strike is not None and
                        abs(self.call_wall_strike - spot_price) <= self.wall_proximity_points and
                        call_vol_surge
                    )

                    signal_ce = self.debouncer.edge("buy_ce", buy_ce_cond)
                    signal_pe = self.debouncer.edge("buy_pe", buy_pe_cond)

                    if (signal_ce or signal_pe) and self.limiter.allow():
                        option_type = "CE" if signal_ce else "PE"
                        reason = "bounce_put_wall" if signal_ce else "reject_call_wall"

                        atm_opt = self.get_option_by_label(chain, "ATM", option_type)

                        if atm_opt:
                            symbol = atm_opt.get("symbol")
                            ltp = safe_float(atm_opt.get("ltp", 0))

                            self.logger.info(format_kv(
                                event="trade",
                                action="BUY",
                                opt=option_type,
                                reason=reason,
                                spot=spot_price,
                                symbol=symbol
                            ))

                            try:
                                resp = self.api_client.placesmartorder(
                                    strategy=self.strategy_name,
                                    symbol=symbol,
                                    action="BUY",
                                    exchange=self.options_exchange,
                                    pricetype="MARKET",
                                    product=self.product,
                                    quantity=self.quantity,
                                    position_size=1
                                )
                                self.logger.info(f"Entry order response: {resp}")

                                # Track position
                                self.tracker.add_legs(
                                    legs=[{"symbol": symbol, "action": "BUY", "quantity": self.quantity}],
                                    entry_prices=[ltp],
                                    side="BUY"
                                )
                                self.limiter.record()

                            except Exception as e:
                                self.logger.error(f"Error placing entry order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyOIWallVolumeSurge().run()
