#!/usr/bin/env python3
"""
Nifty OI Wall + Volume Surge Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Identifies Call and Put OI walls and triggers trades on bounces/rejections confirmed by volume surges (>5000), using a dynamic stop-loss on wall breaches.
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
root_dir = os.path.dirname(strategies_dir)

sys.path.insert(0, root_dir)
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


# API Key retrieval (MANDATORY)
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

# ==========================================
# CONFIGURATION
# ==========================================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "OI_Wall_Volume_Surge")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Risk and Trade Parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "30.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "60.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "20"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "120"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "15"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "3"))

# Strategy specific parameters
VOLUME_SURGE_THRESHOLD = safe_int(os.getenv("VOLUME_SURGE_THRESHOLD", "5000"))
WALL_DISTANCE_PCT = safe_float(os.getenv("WALL_DISTANCE_PCT", "0.2"))  # 0.2% distance from wall

# Allow manual override for expiry
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()


class NiftyOIWallStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
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
        self.expiry = EXPIRY_DATE
        self.last_expiry_check = 0
        self.current_date = datetime.now().date()

        # State tracking for dynamic SL
        self.active_wall_strike = None
        self.active_trade_type = None  # "BOUNCE_SUPPORT" or "REJECT_RESISTANCE"

    def ensure_expiry(self):
        """Fetch nearest expiry if not manually set, refresh periodically."""
        if self.expiry and (time.time() - self.last_expiry_check < EXPIRY_REFRESH_SEC):
            return

        try:
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.last_expiry_check = time.time()
                    self.logger.info(f"Selected expiry: {self.expiry}")
                else:
                    self.logger.warning("No valid future expiry dates found.")
            else:
                self.logger.error(f"Failed to fetch expiry: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Error fetching expiry: {e}")

    def find_oi_walls(self, chain):
        """
        Identify Call OI Wall (Resistance) and Put OI Wall (Support).
        Returns: (call_wall_strike, put_wall_strike)
        """
        max_ce_oi = -1
        max_pe_oi = -1
        ce_wall_strike = None
        pe_wall_strike = None

        for item in chain:
            strike = safe_float(item.get("strike", 0))
            ce_oi = safe_int(item.get("ce", {}).get("oi", 0))
            pe_oi = safe_int(item.get("pe", {}).get("oi", 0))

            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                ce_wall_strike = strike

            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                pe_wall_strike = strike

        return ce_wall_strike, pe_wall_strike

    def get_option_volume(self, chain, strike, option_type):
        """Get volume for a specific option."""
        for item in chain:
            if safe_float(item.get("strike", 0)) == strike:
                return safe_int(item.get(option_type.lower(), {}).get("volume", 0))
        return 0

    def _close_position(self, chain, reason):
        """Close all open legs."""
        self.logger.info(f"Closing position. Reason: {reason}")
        if not self.tracker.open_legs:
            return

        legs_to_close = []
        for leg in self.tracker.open_legs:
            legs_to_close.append({
                "symbol": leg["symbol"],
                "option_type": leg.get("option_type", "CE"), # Default CE if not set
                "action": "SELL" if leg["action"].upper() == "BUY" else "BUY",
                "quantity": leg.get("quantity", QUANTITY),
                "product": PRODUCT
            })

        # Process SELLs first for closing BUY positions
        legs_to_close.sort(key=lambda x: 0 if x["action"] == "SELL" else 1)

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=legs_to_close
            )
            self.logger.info(f"Exit response: {res}")

            # Clear tracker regardless of API success to avoid getting stuck
            # A real prod system might retry, but simple state clear is safer here
            self.tracker.clear()
            self.active_wall_strike = None
            self.active_trade_type = None

        except Exception as e:
            self.logger.error(f"Error closing position: {e}")

    def _execute_entry(self, chain, trade_type, signal_reason, wall_strike):
        """Execute directional entry."""
        self.logger.info(f"Executing Entry: {trade_type} | Reason: {signal_reason}")

        # Determine leg configuration
        if trade_type == "BOUNCE_SUPPORT":
            # Buy ATM CE
            option_type = "CE"
        elif trade_type == "REJECT_RESISTANCE":
            # Buy ATM PE
            option_type = "PE"
        else:
            return

        # Find ATM option
        atm_item = None
        for item in chain:
            if item.get(option_type.lower(), {}).get("label") == "ATM":
                atm_item = item
                break

        if not atm_item:
            self.logger.warning(f"Could not find ATM {option_type} for entry.")
            return

        opt_data = atm_item.get(option_type.lower(), {})
        symbol = opt_data.get("symbol")
        ltp = safe_float(opt_data.get("ltp", 0))

        if not symbol or ltp <= 0:
            self.logger.warning(f"Invalid ATM {option_type} data.")
            return

        api_legs = [
            {
                "symbol": symbol,
                "option_type": option_type,
                "action": "BUY",
                "quantity": QUANTITY,
                "product": PRODUCT
            }
        ]

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=api_legs
            )

            if res.get("status") == "success":
                self.logger.info(f"Entry Order Success: {res}")

                resolved_legs = [{
                    "symbol": symbol,
                    "option_type": option_type,
                    "action": "BUY",
                    "quantity": QUANTITY,
                    "entry_price": ltp
                }]

                self.tracker.add_legs(resolved_legs, [ltp], side="BUY")
                self.active_wall_strike = wall_strike
                self.active_trade_type = trade_type
                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def can_trade(self):
        """Check time constraints."""
        now = datetime.now().time()
        start_time = datetime.strptime("09:30", "%H:%M").time()
        end_time = datetime.strptime("14:30", "%H:%M").time()
        return start_time <= now <= end_time

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} (NIFTY OI Wall + Volume Surge)")

        while True:
            try:
                # 0. Check daily reset
                if datetime.now().date() != self.current_date:
                    self.current_date = datetime.now().date()
                    # Limiter handles its own daily reset, but good practice
                    self.logger.info("New trading day, resetting state.")

                # 1. Check market hours
                market_open = True
                try:
                    market_open = is_market_open()
                except:
                    pass

                if not market_open:
                    time.sleep(60)
                    continue

                # 2. Expiry management
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch data
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=True)
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                spot = safe_float(chain_resp.get("underlying_ltp", 0))

                if spot <= 0:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 4. Exit Management FIRST
                if self.tracker.open_legs:
                    # Normal tracker checks (SL/TP/Time)
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # Custom Dynamic SL based on Wall Breach
                    if not exit_now and self.active_wall_strike:
                        if self.active_trade_type == "BOUNCE_SUPPORT" and spot < self.active_wall_strike:
                            exit_now = True
                            exit_reason = f"wall_breach_support (Spot {spot} < Wall {self.active_wall_strike})"
                        elif self.active_trade_type == "REJECT_RESISTANCE" and spot > self.active_wall_strike:
                            exit_now = True
                            exit_reason = f"wall_breach_resistance (Spot {spot} > Wall {self.active_wall_strike})"

                    # EOD Square-off
                    now = datetime.now().time()
                    eod_time = datetime.strptime("15:15", "%H:%M").time()
                    if now >= eod_time:
                        exit_now = True
                        exit_reason = "eod_square_off"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                    # Log open position status
                    self.logger.info(format_kv(
                        spot=f"{spot:.2f}",
                        wall=f"{self.active_wall_strike}",
                        trade=self.active_trade_type,
                        pos="OPEN"
                    ))
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 5. Calculate Indicators (OI Walls & Volumes)
                ce_wall, pe_wall = self.find_oi_walls(chain)

                if not ce_wall or not pe_wall:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 6. Entry Logic
                if not self.tracker.open_legs and self.can_trade() and self.limiter.allow():
                    dist_to_pe_wall_pct = abs(spot - pe_wall) / pe_wall * 100
                    dist_to_ce_wall_pct = abs(spot - ce_wall) / ce_wall * 100

                    pe_wall_volume = self.get_option_volume(chain, pe_wall, "PE")
                    ce_wall_volume = self.get_option_volume(chain, ce_wall, "CE")

                    self.logger.info(format_kv(
                        spot=f"{spot:.2f}",
                        ce_wall=f"{ce_wall}",
                        pe_wall=f"{pe_wall}",
                        ce_vol=ce_wall_volume,
                        pe_vol=pe_wall_volume,
                        pos="FLAT"
                    ))

                    # Support Bounce Logic
                    # If spot is near PE Wall and PE volume surges (defending the put)
                    is_near_support = (spot >= pe_wall) and (dist_to_pe_wall_pct <= WALL_DISTANCE_PCT)
                    support_bounce_sig = is_near_support and (pe_wall_volume > VOLUME_SURGE_THRESHOLD)

                    # Resistance Reject Logic
                    # If spot is near CE Wall and CE volume surges (defending the call)
                    is_near_resistance = (spot <= ce_wall) and (dist_to_ce_wall_pct <= WALL_DISTANCE_PCT)
                    resist_reject_sig = is_near_resistance and (ce_wall_volume > VOLUME_SURGE_THRESHOLD)

                    if self.debouncer.edge("bounce_support", support_bounce_sig):
                        self._execute_entry(chain, "BOUNCE_SUPPORT", "Spot near PE wall + PE vol surge", pe_wall)
                    elif self.debouncer.edge("reject_resistance", resist_reject_sig):
                        self._execute_entry(chain, "REJECT_RESISTANCE", "Spot near CE wall + CE vol surge", ce_wall)

            except Exception as e:
                self.logger.error(f"Strategy Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftyOIWallStrategy()
    strategy.run()
