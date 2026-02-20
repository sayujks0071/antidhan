#!/usr/bin/env python3
"""
[Nifty Smart OI Reversal] - NIFTY Options (OpenAlgo Web UI Compatible)
Trades reversals from high OI levels (Resistance/Support) with Volume Momentum confirmation.
Logic:
- Identifies Max Call OI (Resistance) and Max Put OI (Support).
- Monitors Spot Price proximity to these walls (Zone: +/- 25 points).
- Bullish Reversal: Spot touches Support Zone, then bounces up (> Support + 10 pts). Confirmed by Call Volume surge.
- Bearish Reversal: Spot touches Resistance Zone, then rejects down (< Resistance - 10 pts). Confirmed by Put Volume surge.
- Risk: SL 20%, TP 40%, Time Stop 45 mins.
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


# API Key retrieval (MANDATORY - place after configuration section)
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


# ===========================
# CONFIGURATION
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftySmartOIReversal")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Strategy Parameters
WALL_PROXIMITY_BUFFER = safe_float(os.getenv("WALL_PROXIMITY_BUFFER", "25.0")) # Zone around wall
REVERSAL_CONFIRMATION = safe_float(os.getenv("REVERSAL_CONFIRMATION", "10.0")) # Points to move away from wall to confirm
VOLUME_SURGE_MULTIPLIER = safe_float(os.getenv("VOLUME_SURGE_MULTIPLIER", "1.2")) # Current interval vol > 1.2x prev

# Risk Parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "20.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "40.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

# Rate Limiting
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "3"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

# Manual Expiry Override
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()


class VolumeTracker:
    """Tracks volume changes between polling intervals."""
    def __init__(self):
        self.last_volumes = {} # {symbol: cumulative_volume}
        self.last_interval_volumes = {} # {symbol: interval_volume}

    def update(self, symbol, current_cumulative_vol):
        current_cumulative_vol = safe_int(current_cumulative_vol)
        last_cum = self.last_volumes.get(symbol, current_cumulative_vol)

        interval_vol = current_cumulative_vol - last_cum

        # Update state
        prev_interval_vol = self.last_interval_volumes.get(symbol, 0)
        self.last_volumes[symbol] = current_cumulative_vol
        self.last_interval_volumes[symbol] = interval_vol

        return interval_vol, prev_interval_vol

    def is_surging(self, symbol, current_cumulative_vol, multiplier=1.2):
        interval_vol, prev_interval_vol = self.update(symbol, current_cumulative_vol)
        if prev_interval_vol > 0 and interval_vol > (prev_interval_vol * multiplier):
            return True
        return False


class NiftySmartOIReversal:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Standard Tracker for Directional Buy
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
        self.vol_tracker = VolumeTracker()

        self.expiry = EXPIRY_DATE
        self.last_expiry_check = 0
        self.current_date = datetime.now().date()

        # State Tracking
        self.was_in_support_zone = False
        self.was_in_resistance_zone = False

    def ensure_expiry(self):
        """Refresh expiry date if needed."""
        if self.expiry and (time.time() - self.last_expiry_check < EXPIRY_REFRESH_SEC):
            return

        if os.getenv("EXPIRY_DATE"):
            self.expiry = os.getenv("EXPIRY_DATE")
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
                    self.logger.warning("No valid future expiry found.")
            else:
                self.logger.error(f"Failed to fetch expiry: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Expiry fetch error: {e}")

    def _close_position(self, chain, reason):
        """Close open position."""
        self.logger.info(f"Closing position. Reason: {reason}")

        if not self.tracker.open_legs:
            return

        # Prepare exit legs (SELL to Close for Long positions)
        legs_to_close = []
        for leg in self.tracker.open_legs:
            close_leg = {
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": "SELL",  # Closing a Buy
                "quantity": leg["quantity"],
                "product": leg.get("product", PRODUCT)
            }
            legs_to_close.append(close_leg)

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
                self.was_in_support_zone = False # Reset state
                self.was_in_resistance_zone = False
            else:
                self.logger.error(f"Exit failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _open_position(self, chain, signal_type, reason):
        """Open Long Call or Put based on signal."""
        self.logger.info(f"Attempting to enter {signal_type} ({reason})...")

        # Determine Option Type
        option_type = "CE" if signal_type == "BULLISH" else "PE"

        # Find ATM Strike for Entry (Liquidity is best at ATM)
        atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)
        if not atm_item:
            self.logger.warning("ATM strike not found in chain.")
            return

        # Get Symbol and LTP
        opt_data = atm_item.get(option_type.lower(), {})
        symbol = opt_data.get("symbol")
        ltp = safe_float(opt_data.get("ltp"))

        if not symbol or ltp <= 0:
            self.logger.warning(f"Invalid symbol or LTP for {option_type}")
            return

        # Prepare Order Leg
        api_legs = [{
            "symbol": symbol,
            "option_type": option_type,
            "action": "BUY",
            "quantity": QUANTITY,
            "product": PRODUCT
        }]

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

                # Add to Tracker
                resolved_legs = [{
                    "symbol": symbol,
                    "option_type": option_type,
                    "action": "BUY",
                    "quantity": QUANTITY,
                    "entry_price": ltp,
                    "product": PRODUCT
                }]

                self.tracker.add_legs(resolved_legs, [ltp], side="BUY")
                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def analyze_chain(self, chain):
        """Find max OI strikes and calculate stats."""
        max_ce_oi = 0
        max_pe_oi = 0
        max_ce_strike = 0
        max_pe_strike = 0

        total_ce_oi = 0
        total_pe_oi = 0

        for item in chain:
            strike = item["strike"]
            ce_oi = safe_int(item.get("ce", {}).get("oi", 0))
            pe_oi = safe_int(item.get("pe", {}).get("oi", 0))

            total_ce_oi += ce_oi
            total_pe_oi += pe_oi

            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                max_ce_strike = strike

            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                max_pe_strike = strike

        pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0

        return {
            "max_ce_strike": max_ce_strike,
            "max_pe_strike": max_pe_strike,
            "pcr": pcr
        }

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING}")

        while True:
            try:
                # 0. Daily Reset
                if datetime.now().date() != self.current_date:
                    self.current_date = datetime.now().date()
                    self.was_in_support_zone = False
                    self.was_in_resistance_zone = False

                # 1. Market Hours Check
                if not is_market_open():
                    time.sleep(60)
                    continue

                # 2. Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch Option Chain
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT,
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=STRIKE_COUNT)
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # 4. Exit Management (Priority)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Exit
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    eod_time = datetime.strptime("15:15", "%H:%M").time()

                    if now.time() >= eod_time:
                        exit_now = True
                        exit_reason = "eod_sqoff"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue
                    else:
                        self.logger.info(format_kv(
                            spot=f"{underlying_ltp:.2f}",
                            pos="OPEN",
                            pnl="TRACKING"
                        ))

                # 5. Entry Logic
                if not self.tracker.open_legs:
                    stats = self.analyze_chain(chain)
                    res_strike = stats["max_ce_strike"]
                    sup_strike = stats["max_pe_strike"]
                    pcr = stats["pcr"]

                    # Zone Logic
                    in_sup_zone = (sup_strike - WALL_PROXIMITY_BUFFER) <= underlying_ltp <= (sup_strike + WALL_PROXIMITY_BUFFER)
                    in_res_zone = (res_strike - WALL_PROXIMITY_BUFFER) <= underlying_ltp <= (res_strike + WALL_PROXIMITY_BUFFER)

                    # Update State
                    if in_sup_zone: self.was_in_support_zone = True
                    if in_res_zone: self.was_in_resistance_zone = True

                    # Reset State if too far away (e.g. 50 pts)
                    if underlying_ltp > (sup_strike + 50): self.was_in_support_zone = False
                    if underlying_ltp < (res_strike - 50): self.was_in_resistance_zone = False

                    self.logger.info(format_kv(
                        spot=f"{underlying_ltp:.2f}",
                        res=res_strike,
                        sup=sup_strike,
                        pcr=f"{pcr:.2f}",
                        in_sup=in_sup_zone,
                        in_res=in_res_zone
                    ))

                    # Trigger Logic: Reversal Confirmation
                    # Bullish: Was in support zone, now bouncing up (> Sup + Confirmation)
                    bullish_reversal = (
                        self.was_in_support_zone and
                        underlying_ltp > (sup_strike + REVERSAL_CONFIRMATION) and
                        pcr > 0.8
                    )

                    # Bearish: Was in resistance zone, now rejecting down (< Res - Confirmation)
                    bearish_reversal = (
                        self.was_in_resistance_zone and
                        underlying_ltp < (res_strike - REVERSAL_CONFIRMATION) and
                        pcr < 1.2
                    )

                    # Volume Confirmation (Check ATM Volume Surge)
                    atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)
                    vol_confirmed = False

                    if atm_item:
                        if bullish_reversal:
                            ce_sym = atm_item.get("ce", {}).get("symbol")
                            ce_vol = atm_item.get("ce", {}).get("volume", 0)
                            if self.vol_tracker.is_surging(ce_sym, ce_vol, VOLUME_SURGE_MULTIPLIER):
                                vol_confirmed = True
                        elif bearish_reversal:
                            pe_sym = atm_item.get("pe", {}).get("symbol")
                            pe_vol = atm_item.get("pe", {}).get("volume", 0)
                            if self.vol_tracker.is_surging(pe_sym, pe_vol, VOLUME_SURGE_MULTIPLIER):
                                vol_confirmed = True

                    # Debounce
                    entry_long = self.debouncer.edge("long_signal", bullish_reversal and vol_confirmed)
                    entry_short = self.debouncer.edge("short_signal", bearish_reversal and vol_confirmed)

                    if self.limiter.allow():
                        if entry_long:
                            self._open_position(chain, "BULLISH", f"bounce_sup_{sup_strike}_vol_surge")
                        elif entry_short:
                            self._open_position(chain, "BEARISH", f"reject_res_{res_strike}_vol_surge")

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftySmartOIReversal()
    strategy.run()
