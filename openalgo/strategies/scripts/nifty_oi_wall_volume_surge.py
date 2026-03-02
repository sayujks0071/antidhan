#!/usr/bin/env python3
"""
[Nifty OI Wall + Volume Surge] - NIFTY Options (OpenAlgo Web UI Compatible)
Identifies major OI walls (Support/Resistance) and enters trades when price bounces/rejects with volume surge.
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


# Configuration parameters
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyOIWallVolSurge")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Risk Parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "25.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "20"))

# Trading hours/limits
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "5"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "10"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

class NiftyOIWallVolumeSurge:
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
        self.expiry = os.getenv("EXPIRY_DATE", "").strip()
        self.last_expiry_check = 0 if not self.expiry else time.time()
        self.manual_expiry = bool(self.expiry)
        self.entered_today = False

        # Track active wall for dynamic SL
        self.active_wall_strike = None
        self.active_wall_type = None

        # To track volume changes
        self.previous_volume_data = {}

    def ensure_expiry(self):
        if self.manual_expiry:
            return

        if self.expiry and (time.time() - self.last_expiry_check < EXPIRY_REFRESH_SEC):
            return

        self.logger.info("Fetching available expiry dates...")
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
                self.logger.error(f"Failed to fetch expiry: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Expiry fetch error: {e}")

    def get_oi_walls(self, chain):
        """Identify Call and Put OI walls."""
        max_ce_oi = -1
        max_pe_oi = -1
        ce_wall_strike = 0
        pe_wall_strike = 0

        for item in chain:
            strike = safe_float(item.get("strike", 0))
            ce = item.get("ce", {})
            pe = item.get("pe", {})

            ce_oi = safe_int(ce.get("oi", 0))
            pe_oi = safe_int(pe.get("oi", 0))

            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                ce_wall_strike = strike

            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                pe_wall_strike = strike

        return ce_wall_strike, pe_wall_strike

    def detect_volume_surge(self, chain):
        """Detect if there is a volume surge on specific strikes."""
        surge_detected_strike = None
        surge_type = None  # 'CE' or 'PE'

        for item in chain:
            strike = safe_float(item.get("strike", 0))
            ce = item.get("ce", {})
            pe = item.get("pe", {})

            ce_vol = safe_int(ce.get("volume", 0))
            pe_vol = safe_int(pe.get("volume", 0))

            if strike in self.previous_volume_data:
                prev_ce_vol = self.previous_volume_data[strike]['ce']
                prev_pe_vol = self.previous_volume_data[strike]['pe']

                ce_vol_diff = ce_vol - prev_ce_vol
                pe_vol_diff = pe_vol - prev_pe_vol

                # Detect abnormal volume spike in a single tick (e.g., > 5000 contracts in 10s)
                if ce_vol_diff > 5000:
                    surge_detected_strike = strike
                    surge_type = 'CE'
                elif pe_vol_diff > 5000:
                    surge_detected_strike = strike
                    surge_type = 'PE'

            # Update history
            self.previous_volume_data[strike] = {'ce': ce_vol, 'pe': pe_vol}

        return surge_detected_strike, surge_type

    def _close_position(self, chain, exit_reason):
        if not self.tracker.open_legs:
            return

        self.logger.info(f"Closing position. Reason: {exit_reason}")
        legs_to_close = []
        for leg in self.tracker.open_legs:
            legs_to_close.append({
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": "SELL" if leg["action"] == "BUY" else "BUY",
                "quantity": leg["quantity"],
                "product": leg.get("product", PRODUCT)
            })

        # Ensure BUY actions are processed first
        legs_to_close.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=legs_to_close
            )
            self.logger.info(f"Exit Order Response: {res}")
            if res.get("status") == "success":
                self.tracker.clear()
                self.active_wall_strike = None
                self.active_wall_type = None
            else:
                self.logger.error(f"Exit failed: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _open_position(self, chain, option_type_to_buy, reason, wall_strike, wall_type):
        self.logger.info(f"Opening position. Reason: {reason}")

        # Buy ATM Option
        atm_item = None
        for item in chain:
            opt = item.get(option_type_to_buy.lower(), {})
            if opt.get("label") == "ATM":
                atm_item = opt
                break

        if not atm_item:
            self.logger.warning(f"Could not find ATM {option_type_to_buy}")
            return

        symbol = atm_item.get("symbol")
        ltp = safe_float(atm_item.get("ltp"))

        api_leg = {
            "offset": "ATM",
            "option_type": option_type_to_buy,
            "action": "BUY",
            "quantity": QUANTITY,
            "product": PRODUCT
        }

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=[api_leg]
            )
            if res.get("status") == "success":
                self.logger.info(f"Entry Order Success: {res}")

                # Use actual symbol and price for local position tracking
                tracker_leg = {
                    "symbol": symbol,
                    "option_type": option_type_to_buy,
                    "action": "BUY",
                    "quantity": QUANTITY,
                    "product": PRODUCT,
                    "entry_price": ltp
                }

                self.tracker.add_legs([tracker_leg], [ltp], side="BUY")
                self.limiter.record()

                self.active_wall_strike = wall_strike
                self.active_wall_type = wall_type
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # Time filters
                now = datetime.now()
                current_time = now.strftime("%H:%M")

                # Check if market is open
                market_open = True
                try:
                    if not is_market_open():
                        market_open = False
                except:
                    pass

                if not market_open:
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=STRIKE_COUNT)
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                spot = safe_float(chain_resp.get("underlying_ltp", 0))

                # EXITS
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    if current_time >= "15:15":
                        exit_now = True
                        exit_reason = "eod_square_off"

                    # Dynamic SL based on wall breach
                    if not exit_now and self.active_wall_strike and self.active_wall_type:
                        if self.active_wall_type == 'PE' and spot < self.active_wall_strike:
                            exit_now = True
                            exit_reason = f"dynamic_sl_support_breached ({spot} < {self.active_wall_strike})"
                        elif self.active_wall_type == 'CE' and spot > self.active_wall_strike:
                            exit_now = True
                            exit_reason = f"dynamic_sl_resistance_breached ({spot} > {self.active_wall_strike})"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # ENTRIES
                if not self.tracker.open_legs and "09:30" <= current_time <= "14:30":
                    if self.limiter.allow():
                        ce_wall, pe_wall = self.get_oi_walls(chain)
                        surge_strike, surge_type = self.detect_volume_surge(chain)

                        self.logger.info(format_kv(
                            spot=f"{spot:.2f}",
                            ce_wall=ce_wall,
                            pe_wall=pe_wall,
                            surge_strike=surge_strike,
                            surge_type=surge_type
                        ))

                        signal = None
                        reason = ""
                        wall_strike = None
                        wall_type = None

                        # If spot approaches PE Wall (Support) and bounces with Put Volume Surge => Buy CE
                        if pe_wall > 0 and abs(spot - pe_wall) <= 50:
                            if surge_strike == pe_wall and surge_type == 'PE':
                                signal = "CE"
                                reason = "Bounce off PE Support with Volume Surge"
                                wall_strike = pe_wall
                                wall_type = 'PE'

                        # If spot approaches CE Wall (Resistance) and rejects with Call Volume Surge => Buy PE
                        elif ce_wall > 0 and abs(spot - ce_wall) <= 50:
                            if surge_strike == ce_wall and surge_type == 'CE':
                                signal = "PE"
                                reason = "Rejection off CE Resistance with Volume Surge"
                                wall_strike = ce_wall
                                wall_type = 'CE'

                        is_signal = bool(signal)
                        if self.debouncer.edge("entry", is_signal) and is_signal:
                            self._open_position(chain, signal, reason, wall_strike, wall_type)

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    strategy = NiftyOIWallVolumeSurge()
    strategy.run()
