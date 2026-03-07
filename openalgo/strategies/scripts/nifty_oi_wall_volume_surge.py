#!/usr/bin/env python3
"""
NIFTY OI Wall + Volume Surge Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Identifies the strike with maximum Call OI (resistance) and Put OI (support). Enters when spot bounces off support or rejects from resistance confirmed by volume surge.

CHANGELOG:
- 2026-02-23: Initial version following standard templates and constraints.
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

# Add root dir for potential project-level imports
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

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


class NiftyOiWallVolumeSurgeStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_OI_Wall_Surge")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.exchange_underlying = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.exchange_options = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        # Risk management parameters
        self.sl_pct = safe_float(os.getenv("SL_PCT", "30"), 30.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "60"), 60.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "20"), 20)

        # Strategy specific thresholds
        self.volume_surge_threshold = safe_float(os.getenv("VOLUME_SURGE_THRESHOLD", "5000"), 5000.0)
        self.wall_distance_threshold = safe_float(os.getenv("WALL_DISTANCE_THRESHOLD", "50"), 50.0)

        # Time management
        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "60"), 60)
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "15"), 15)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "300"), 300)
        self.max_orders_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "10"), 10)
        self.max_orders_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "3"), 3)

        # State
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_day,
            max_per_hour=self.max_orders_hour,
            cooldown_seconds=self.cooldown_seconds
        )

        self.expiry = normalize_expiry(os.getenv("EXPIRY_DATE", ""))
        self.last_expiry_check = 0
        self.entered_today = 0

        # Volume tracking
        self.last_volumes = {} # strike -> volume

        self.logger.info(format_kv(
            msg="Strategy initialized",
            underlying=self.underlying,
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold=self.max_hold_min,
            vol_thresh=self.volume_surge_threshold,
            wall_dist=self.wall_distance_threshold
        ))

    def ensure_expiry(self):
        """Resolves the nearest expiry if not set or refreshes periodically."""
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.exchange_options, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    nearest = choose_nearest_expiry(dates)
                    if nearest and nearest != self.expiry:
                        self.expiry = nearest
                        self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                self.last_expiry_check = now
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        """Checks if current time is within trading window and limits allow."""
        if not is_market_open():
            return False

        now = datetime.now().time()

        # Only trade between 9:30 AM and 2:30 PM
        if now < datetime.strptime("09:30", "%H:%M").time():
            return False
        if now > datetime.strptime("14:30", "%H:%M").time():
            return False

        return self.limiter.allow()

    def identify_oi_walls(self, chain):
        """Find strikes with highest Call OI (resistance) and Put OI (support)."""
        max_ce_oi = -1
        max_pe_oi = -1
        ce_wall_strike = None
        pe_wall_strike = None

        for item in chain:
            strike = item["strike"]
            ce_oi = safe_int(item.get("ce", {}).get("oi", 0))
            pe_oi = safe_int(item.get("pe", {}).get("oi", 0))

            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                ce_wall_strike = strike

            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                pe_wall_strike = strike

        return ce_wall_strike, pe_wall_strike, max_ce_oi, max_pe_oi

    def _close_position(self, chain, reason):
        """Closes all open legs."""
        if not self.tracker.open_legs:
            return

        self.logger.info(format_kv(event="exit_triggered", reason=reason))

        # We need to close single legs using APIClient.placesmartorder
        from trading_utils import APIClient
        api_client = APIClient(api_key=API_KEY, host=HOST)

        for leg in self.tracker.open_legs:
            exit_action = "SELL" if leg["action"] == "BUY" else "BUY"

            try:
                res = api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=exit_action,
                    exchange=self.exchange_options,
                    pricetype="MARKET",
                    product=leg["product"],
                    quantity=leg["quantity"],
                    position_size=leg["quantity"]
                )
                self.logger.info(f"Trade response (Exit {leg['symbol']}): {res}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()

    def _place_entry_order(self, chain, spot_price, option_type, wall_strike, atm_strike):
        """Executes the entry order."""
        action = "BUY"
        offset = "ATM" # Assuming we buy ATM options for momentum

        # To find the ATM symbol for tracking entry prices
        entry_symbol = None
        entry_price = 0.0

        for item in chain:
            if item["strike"] == atm_strike:
                if option_type == "CE":
                    entry_symbol = item.get("ce", {}).get("symbol")
                    entry_price = safe_float(item.get("ce", {}).get("ltp", 0))
                else:
                    entry_symbol = item.get("pe", {}).get("symbol")
                    entry_price = safe_float(item.get("pe", {}).get("ltp", 0))
                break

        if not entry_symbol or entry_price <= 0:
            self.logger.warning("Could not resolve entry symbol or price.")
            return

        # OpenAlgo API does not expect "symbol" in the legs list for optionsmultiorder.
        # We'll pass it to API without symbol, but we need it for the tracker.
        api_legs = [{
            "offset": offset,
            "option_type": option_type,
            "action": action,
            "quantity": self.quantity,
            "product": self.product
        }]

        tracker_legs = [{
            "offset": offset,
            "option_type": option_type,
            "action": action,
            "quantity": self.quantity,
            "product": self.product,
            "symbol": entry_symbol
        }]

        self.logger.info(format_kv(
            event="trade",
            signal=f"BUY_{option_type}",
            spot=spot_price,
            wall=wall_strike,
            atm_strike=atm_strike,
            price=entry_price
        ))

        try:
            res = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.exchange_options,
                expiry_date=self.expiry,
                legs=api_legs
            )
            self.logger.info(f"Trade response (Entry): {res}")

            # Add to position tracker
            if res.get("status") == "success":
                self.tracker.add_legs(tracker_legs, [entry_price], side="BUY")
                self.limiter.record()
                self.entered_today += 1
        except Exception as e:
            self.logger.error(f"Error placing entry order: {e}")

    def run(self):
        """Main strategy loop."""
        self.logger.info("Starting Nifty OI Wall + Volume Surge Strategy Loop.")

        while True:
            try:
                # EOD Square-off
                now = datetime.now().time()
                if now >= datetime.strptime("15:15", "%H:%M").time() and self.tracker.open_legs:
                    self.logger.info("EOD Square-off triggered.")
                    self._close_position([], "eod_squareoff")

                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # Fetch Option Chain
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.exchange_underlying,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=self.strike_count, require_oi=True, require_volume=True)
                if not valid:
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")
                spot_price = safe_float(chain_resp.get("underlying_ltp"))

                if not atm_strike or not spot_price:
                    time.sleep(self.sleep_seconds)
                    continue

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # Add dynamic SL on wall breach
                    # If we hold CE (Bullish), and spot drops below our PE wall (Support), exit
                    # If we hold PE (Bearish), and spot rises above our CE wall (Resistance), exit
                    if not exit_now and len(self.tracker.open_legs) > 0:
                        ce_wall, pe_wall, _, _ = self.identify_oi_walls(chain)
                        option_held = self.tracker.open_legs[0].get("option_type")
                        if option_held == "CE" and pe_wall and spot_price < pe_wall:
                            exit_now = True
                            exit_reason = "support_wall_breach"
                        elif option_held == "PE" and ce_wall and spot_price > ce_wall:
                            exit_now = True
                            exit_reason = "resistance_wall_breach"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    ce_wall_strike, pe_wall_strike, max_ce_oi, max_pe_oi = self.identify_oi_walls(chain)

                    if not ce_wall_strike or not pe_wall_strike:
                        continue

                    # Track volume surges (Delta volume between intervals)
                    ce_wall_volume = 0
                    pe_wall_volume = 0
                    for item in chain:
                        if item["strike"] == ce_wall_strike:
                            ce_wall_volume = safe_float(item.get("ce", {}).get("volume", 0))
                        if item["strike"] == pe_wall_strike:
                            pe_wall_volume = safe_float(item.get("pe", {}).get("volume", 0))

                    # Get last known volume
                    last_ce_vol = self.last_volumes.get(f"{ce_wall_strike}_CE", ce_wall_volume)
                    last_pe_vol = self.last_volumes.get(f"{pe_wall_strike}_PE", pe_wall_volume)

                    # Calculate volume surge (delta)
                    ce_vol_delta = ce_wall_volume - last_ce_vol
                    pe_vol_delta = pe_wall_volume - last_pe_vol

                    # Update state
                    self.last_volumes[f"{ce_wall_strike}_CE"] = ce_wall_volume
                    self.last_volumes[f"{pe_wall_strike}_PE"] = pe_wall_volume

                    # Check CE Resistance Wall Rejection (Bearish -> Buy PE)
                    ce_dist = ce_wall_strike - spot_price
                    near_ce_wall = (0 <= ce_dist <= self.wall_distance_threshold)
                    ce_vol_surge = ce_vol_delta > self.volume_surge_threshold

                    reject_signal = self.debouncer.edge("reject_ce_wall", bool(near_ce_wall and ce_vol_surge))

                    # Check PE Support Wall Bounce (Bullish -> Buy CE)
                    pe_dist = spot_price - pe_wall_strike
                    near_pe_wall = (0 <= pe_dist <= self.wall_distance_threshold)
                    pe_vol_surge = pe_vol_delta > self.volume_surge_threshold

                    bounce_signal = self.debouncer.edge("bounce_pe_wall", bool(near_pe_wall and pe_vol_surge))

                    if reject_signal:
                        self.logger.info(format_kv(spot=spot_price, event="ce_wall_reject", ce_wall=ce_wall_strike, vol_surge=ce_vol_delta))
                        self._place_entry_order(chain, spot_price, "PE", ce_wall_strike, atm_strike)
                    elif bounce_signal:
                        self.logger.info(format_kv(spot=spot_price, event="pe_wall_bounce", pe_wall=pe_wall_strike, vol_surge=pe_vol_delta))
                        self._place_entry_order(chain, spot_price, "CE", pe_wall_strike, atm_strike)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    strategy = NiftyOiWallVolumeSurgeStrategy()
    strategy.run()
