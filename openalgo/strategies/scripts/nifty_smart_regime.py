#!/usr/bin/env python3
"""
[Nifty Smart Regime] - NIFTY Options (OpenAlgo Web UI Compatible)
Adaptive Options Strategy: Iron Condor (Neutral), Bull Put Spread (Bullish), Bear Call Spread (Bearish).
Logic:
- Uses PCR (Put-Call Ratio) and OI Walls to detect market regime.
- Neutral (PCR 0.8-1.2, Spot inside Walls): Sell OTM2 CE/PE, Buy OTM4 CE/PE (Iron Condor).
- Bullish (PCR > 1.2, Spot > Support): Sell OTM1 PE, Buy OTM3 PE (Bull Put Spread).
- Bearish (PCR < 0.8, Spot < Resistance): Sell OTM1 CE, Buy OTM3 CE (Bear Call Spread).
- Risk: SL 40%, TP 60% of collected premium. Max Hold 45 mins. EOD Exit 15:15.
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
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftySmartRegime")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Strategy Logic Parameters
PCR_BULLISH = safe_float(os.getenv("PCR_BULLISH", "1.2"))
PCR_BEARISH = safe_float(os.getenv("PCR_BEARISH", "0.8"))
WALL_BUFFER = safe_float(os.getenv("WALL_BUFFER", "25.0")) # Points buffer around OI walls

# Risk Parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "40.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "60.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

# Rate Limiting
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "3"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

# Manual Expiry Override
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()


class NiftySmartRegime:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Tracker for positions (Credit Strategies -> side="SELL")
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

        # Prepare exit legs
        # If we SOLD to Open (Credit), we BUY to Close.
        # If we BOUGHT to Open (Debit), we SELL to Close.
        # OptionPositionTracker stores the opening action.

        legs_to_close = []
        for leg in self.tracker.open_legs:
            open_action = leg["action"].upper()
            close_action = "BUY" if open_action == "SELL" else "SELL"

            close_leg = {
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": close_action,
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
            else:
                self.logger.error(f"Exit failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def resolve_legs_for_regime(self, chain, regime):
        """
        Identify symbols for the strategy based on regime.
        Neutral: Iron Condor (Sell OTM2, Buy OTM4)
        Bullish: Bull Put Spread (Sell OTM1 PE, Buy OTM3 PE)
        Bearish: Bear Call Spread (Sell OTM1 CE, Buy OTM3 CE)
        """
        # Find ATM index
        # We sort chain by strike just in case
        sorted_chain = sorted(chain, key=lambda x: x["strike"])

        atm_idx = -1
        for i, item in enumerate(sorted_chain):
            if (item.get("ce") or {}).get("label") == "ATM":
                atm_idx = i
                break

        if atm_idx == -1:
            self.logger.warning("ATM strike not found in chain.")
            return []

        legs = []

        try:
            if regime == "NEUTRAL":
                # Iron Condor: Sell OTM2 CE/PE, Buy OTM4 CE/PE
                # PE side (Strikes below ATM)
                pe_short = sorted_chain[atm_idx - 2].get("pe", {})
                pe_long  = sorted_chain[atm_idx - 4].get("pe", {})
                # CE side (Strikes above ATM)
                ce_short = sorted_chain[atm_idx + 2].get("ce", {})
                ce_long  = sorted_chain[atm_idx + 4].get("ce", {})

                if pe_short and pe_long and ce_short and ce_long:
                    legs.append(self._create_leg(pe_short, "PE", "SELL"))
                    legs.append(self._create_leg(ce_short, "CE", "SELL"))
                    legs.append(self._create_leg(pe_long, "PE", "BUY"))
                    legs.append(self._create_leg(ce_long, "CE", "BUY"))

            elif regime == "BULLISH":
                # Bull Put Spread: Sell OTM1 PE, Buy OTM3 PE
                pe_short = sorted_chain[atm_idx - 1].get("pe", {})
                pe_long  = sorted_chain[atm_idx - 3].get("pe", {})

                if pe_short and pe_long:
                    legs.append(self._create_leg(pe_short, "PE", "SELL"))
                    legs.append(self._create_leg(pe_long, "PE", "BUY"))

            elif regime == "BEARISH":
                # Bear Call Spread: Sell OTM1 CE, Buy OTM3 CE
                ce_short = sorted_chain[atm_idx + 1].get("ce", {})
                ce_long  = sorted_chain[atm_idx + 3].get("ce", {})

                if ce_short and ce_long:
                    legs.append(self._create_leg(ce_short, "CE", "SELL"))
                    legs.append(self._create_leg(ce_long, "CE", "BUY"))

        except IndexError:
            self.logger.warning("Not enough strikes to form strategy legs.")
            return []

        return legs

    def _create_leg(self, opt_data, opt_type, action):
        return {
            "symbol": opt_data.get("symbol"),
            "option_type": opt_type,
            "action": action,
            "quantity": QUANTITY,
            "product": PRODUCT,
            "ltp": safe_float(opt_data.get("ltp")) # Include LTP for tracker
        }

    def _open_position(self, chain, regime, reason):
        """Execute entry for the given regime."""
        self.logger.info(f"Attempting to enter {regime} ({reason})...")

        legs = self.resolve_legs_for_regime(chain, regime)
        if not legs:
            self.logger.warning("Could not resolve legs.")
            return

        # API expects legs without 'ltp' key usually, but it ignores extra keys.
        # We need to construct API payload.
        api_legs = []
        tracker_legs = []
        entry_prices = []

        # Sort legs: BUY first for margin benefit
        legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        for leg in legs:
            if not leg.get("symbol"):
                self.logger.warning("Missing symbol in leg.")
                return

            api_leg = {
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": leg["action"],
                "quantity": leg["quantity"],
                "product": leg["product"]
            }
            api_legs.append(api_leg)
            tracker_legs.append(api_leg)
            entry_prices.append(leg["ltp"])

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
                # Add to Tracker (Side="SELL" for credit strategies)
                self.tracker.add_legs(tracker_legs, entry_prices, side="SELL")
                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def analyze_chain(self, chain):
        """Find max OI strikes and calculate PCR."""
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
                    self.tracker.clear() # Reset tracker
                    self.limiter = TradeLimiter( # Reset limiter
                        max_per_day=MAX_ORDERS_PER_DAY,
                        max_per_hour=MAX_ORDERS_PER_HOUR,
                        cooldown_seconds=COOLDOWN_SECONDS
                    )

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
                    # Using a simple time check for 15:15 IST
                    # Assuming system time is IST or handling conversion
                    # Here we use datetime.now() assuming server time is set correctly or relative time
                    # Best practice: use offset aware
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now_ist = datetime.now(ist_offset)
                    eod_time = now_ist.replace(hour=15, minute=15, second=0, microsecond=0)

                    if now_ist >= eod_time:
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

                    # Regime Detection
                    regime = "NEUTRAL"
                    signal_reason = ""

                    # Check for Trending
                    is_bullish = pcr > PCR_BULLISH and underlying_ltp > (sup_strike + WALL_BUFFER)
                    is_bearish = pcr < PCR_BEARISH and underlying_ltp < (res_strike - WALL_BUFFER)

                    # Check for Neutral (Inside Walls)
                    is_neutral = (
                        (PCR_BEARISH <= pcr <= PCR_BULLISH) and
                        (underlying_ltp > sup_strike) and
                        (underlying_ltp < res_strike)
                    )

                    if is_bullish:
                        regime = "BULLISH"
                        signal_reason = f"pcr_{pcr:.2f}_>_{PCR_BULLISH}_and_spot_>_sup"
                    elif is_bearish:
                        regime = "BEARISH"
                        signal_reason = f"pcr_{pcr:.2f}_<_{PCR_BEARISH}_and_spot_<_res"
                    elif is_neutral:
                        regime = "NEUTRAL"
                        signal_reason = f"pcr_neutral_and_in_range"
                    else:
                        regime = "WAIT" # No clear signal

                    self.logger.info(format_kv(
                        spot=f"{underlying_ltp:.2f}",
                        res=res_strike,
                        sup=sup_strike,
                        pcr=f"{pcr:.2f}",
                        regime=regime
                    ))

                    # Debounce Signals
                    # We debounce specific regime transitions
                    entry_bull = self.debouncer.edge("bull_signal", regime == "BULLISH")
                    entry_bear = self.debouncer.edge("bear_signal", regime == "BEARISH")
                    entry_neutral = self.debouncer.edge("neutral_signal", regime == "NEUTRAL")

                    # Entry Execution
                    if self.limiter.allow():
                        # Prefer directional over neutral if both trigger (unlikely due to logic)
                        if entry_bull:
                            self._open_position(chain, "BULLISH", signal_reason)
                        elif entry_bear:
                            self._open_position(chain, "BEARISH", signal_reason)
                        elif entry_neutral:
                            self._open_position(chain, "NEUTRAL", signal_reason)

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftySmartRegime()
    strategy.run()
