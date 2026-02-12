#!/usr/bin/env python3
"""
SENSEX Smart OI Hybrid - Innovative OI Wall + PCR Strategy
Combines Put-Call Ratio (PCR) sentiment with Open Interest (OI) Walls for high-probability reversals.

Exchange: BFO (BSE F&O)
Underlying: SENSEX on BSE_INDEX
Expiry: Weekly Friday
Edge: Mean reversion from OI Walls supported by PCR sentiment.
      - Bullish: PCR > 1.2 (Put Support) + Spot near Put Wall -> Buy CE
      - Bearish: PCR < 0.8 (Call Resistance) + Spot near Call Wall -> Buy PE
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone, time as time_obj

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
# Also add local strategies/utils if present (where we put our files)
sys.path.insert(0, os.path.join(script_dir, "utils"))

try:
    from trading_utils import is_market_open
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        safe_float,
        safe_int,
    )
    from strategy_common import (
        SignalDebouncer,
        TradeLimiter,
        format_kv,
    )
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)

# Local fallback for is_market_open to avoid dependencies
def is_market_open_local():
    """Checks if market is open (9:15 - 15:30 IST)."""
    try:
        # IST = UTC + 5:30
        utc_now = datetime.now(timezone.utc)
        ist_now = utc_now + timedelta(hours=5, minutes=30)

        if ist_now.weekday() >= 5: # Sat/Sun
            return False

        now_time = ist_now.time()
        start = time_obj(9, 15)
        end = time_obj(15, 30)
        return start <= now_time <= end
    except Exception:
        return True

class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)

# ===========================
# CONFIGURATION - SENSEX SMART OI HYBRID
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "sensex_smart_oi_hybrid")
UNDERLYING = os.getenv("UNDERLYING", "SENSEX")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "BSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "BFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "15")) # Wider view for OI walls

# Strategy Logic Parameters
PCR_BULLISH = float(os.getenv("PCR_BULLISH", "1.2"))
PCR_BEARISH = float(os.getenv("PCR_BEARISH", "0.8"))
WALL_PROXIMITY = float(os.getenv("WALL_PROXIMITY", "150.0")) # Points near wall to trigger

# Risk Parameters
SL_PCT = float(os.getenv("SL_PCT", "25.0"))
TP_PCT = float(os.getenv("TP_PCT", "60.0"))
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "20"))

# Time & Rate Limits
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:30")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:45")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "15"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "5"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

# Manual Expiry
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

# Defensive Normalization
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and UNDERLYING_EXCHANGE.upper() == "NSE_INDEX":
    UNDERLYING_EXCHANGE = "BSE_INDEX"
if UNDERLYING.upper().startswith(("SENSEX", "BANKEX")) and OPTIONS_EXCHANGE.upper() == "NFO":
    OPTIONS_EXCHANGE = "BFO"

# ===========================
# API KEY RETRIEVAL
# ===========================
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


class SensexSmartOIHybrid:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
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

        self.expiry = EXPIRY_DATE if EXPIRY_DATE else None
        self.last_expiry_check = 0
        self.entered_today = False # Not strictly single-entry, but managed by Limiter

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")
        self.logger.info(format_kv(
            underlying=UNDERLYING,
            pcr_bull=PCR_BULLISH,
            pcr_bear=PCR_BEARISH,
            wall_dist=WALL_PROXIMITY
        ))

    def ensure_expiry(self):
        if EXPIRY_DATE:
            self.expiry = EXPIRY_DATE
            return

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
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def is_time_window_open(self):
        utc_now = datetime.now(timezone.utc)
        ist_now = utc_now + timedelta(hours=5, minutes=30)
        now_time = ist_now.time()
        try:
            start = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
            end = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()
            return start <= now_time <= end
        except ValueError:
            return False

    def get_oi_stats(self, chain):
        """Calculates PCR and identifies max OI walls."""
        total_ce_oi = 0
        total_pe_oi = 0
        max_ce_oi = 0
        max_pe_oi = 0
        call_wall_strike = 0
        put_wall_strike = 0

        for item in chain:
            strike = item["strike"]
            ce_oi = safe_int(item.get("ce", {}).get("oi", 0))
            pe_oi = safe_int(item.get("pe", {}).get("oi", 0))

            total_ce_oi += ce_oi
            total_pe_oi += pe_oi

            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                call_wall_strike = strike

            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                put_wall_strike = strike

        pcr = (total_pe_oi / total_ce_oi) if total_ce_oi > 0 else 0.0
        return {
            "pcr": round(pcr, 2),
            "call_wall": call_wall_strike,
            "put_wall": put_wall_strike,
            "max_ce_oi": max_ce_oi,
            "max_pe_oi": max_pe_oi
        }

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position. Reason: {reason}")
        if not self.tracker.open_legs:
            return

        exit_legs = []
        for leg in self.tracker.open_legs:
            # Reverse action: BUY -> SELL
            exit_legs.append({
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "offset": leg.get("offset", "ATM"),
                "action": "SELL",
                "quantity": leg["quantity"],
                "product": PRODUCT
            })

        try:
            response = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=UNDERLYING_EXCHANGE,
                expiry_date=self.expiry,
                legs=exit_legs
            )
            self.logger.info(f"Exit Response: {response}")
        except Exception as e:
            self.logger.error(f"Exit Failed: {e}")

        self.tracker.clear()

    def _open_position(self, chain, signal_type, reason):
        """Opens a directional position (Long Call or Long Put)."""
        # Bullish -> Buy CE ATM
        # Bearish -> Buy PE ATM

        option_type = "CE" if signal_type == "BULLISH" else "PE"

        # Find ATM leg
        atm_item = next((x for x in chain if x.get("ce", {}).get("label") == "ATM"), None)
        if not atm_item:
            self.logger.warning("ATM strike not found.")
            return

        details = atm_item.get(option_type.lower(), {})
        symbol = details.get("symbol")
        ltp = safe_float(details.get("ltp", 0))

        if not symbol or ltp <= 0:
            self.logger.warning(f"Invalid ATM option: {symbol} @ {ltp}")
            return

        leg = {
            "offset": "ATM",
            "option_type": option_type,
            "action": "BUY",
            "quantity": QUANTITY,
            "product": PRODUCT
        }

        try:
            response = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=UNDERLYING_EXCHANGE,
                expiry_date=self.expiry,
                legs=[leg]
            )

            if response.get("status") == "success":
                self.logger.info(f"Entry Success: {response}")
                self.limiter.record()

                # Add to tracker
                track_leg = leg.copy()
                track_leg["symbol"] = symbol
                self.tracker.add_legs([track_leg], [ltp], side="BUY")
                self.logger.info(f"Position tracked: {signal_type} ({reason})")
            else:
                self.logger.error(f"Entry Failed: {response.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry Error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME}...")

        while True:
            try:
                if not is_market_open_local():
                    self.logger.debug("Market closed.")
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # Fetch Chain
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT,
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10)
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # 1. Exit Management
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        continue

                    # Check EOD
                    utc_now = datetime.now(timezone.utc)
                    ist_now = utc_now + timedelta(hours=5, minutes=30)
                    if ist_now.time() >= datetime.strptime(EXIT_TIME, "%H:%M").time():
                        self._close_position(chain, "EOD_SQUAREOFF")
                        continue

                # 2. Indicators (OI & PCR)
                stats = self.get_oi_stats(chain)
                pcr = stats["pcr"]
                call_wall = stats["call_wall"]
                put_wall = stats["put_wall"]

                dist_to_call_wall = abs(call_wall - underlying_ltp)
                dist_to_put_wall = abs(put_wall - underlying_ltp)

                self.logger.info(format_kv(
                    spot=f"{underlying_ltp:.1f}",
                    pcr=pcr,
                    c_wall=call_wall,
                    p_wall=put_wall,
                    pos="OPEN" if self.tracker.open_legs else "FLAT"
                ))

                # 3. Entry Logic
                if not self.tracker.open_legs and self.limiter.allow() and self.is_time_window_open():

                    # Logic 1: Bullish Reversal (PCR High + At Support)
                    # Support holds -> Buy CE
                    is_bullish = (pcr >= PCR_BULLISH) and (dist_to_put_wall <= WALL_PROXIMITY)

                    # Logic 2: Bearish Reversal (PCR Low + At Resistance)
                    # Resistance holds -> Buy PE
                    is_bearish = (pcr <= PCR_BEARISH) and (dist_to_call_wall <= WALL_PROXIMITY)

                    # Debounce
                    bull_signal = self.debouncer.edge("bull_entry", is_bullish)
                    bear_signal = self.debouncer.edge("bear_entry", is_bearish)

                    if bull_signal:
                        self.logger.info(f"Signal BULLISH: PCR {pcr} >= {PCR_BULLISH} & Spot near Put Wall {put_wall}")
                        self._open_position(chain, "BULLISH", "PCR_SUPPORT_BOUNCE")

                    elif bear_signal:
                        self.logger.info(f"Signal BEARISH: PCR {pcr} <= {PCR_BEARISH} & Spot near Call Wall {call_wall}")
                        self._open_position(chain, "BEARISH", "PCR_RESISTANCE_REJECT")

            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Error: {e}")
                time.sleep(SLEEP_SECONDS)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    SensexSmartOIHybrid().run()
