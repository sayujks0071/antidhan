#!/usr/bin/env python3
"""
[Nifty Smart Multi-Regime] - NIFTY Options (OpenAlgo Web UI Compatible)
Adapts to Bullish (Bull Put), Bearish (Bear Call), or Neutral (Iron Condor) regimes.
Logic:
- Regime Detection via EMA(20) Trend and PCR Sentiment.
- Filters entries using Max OI Support/Resistance Walls to avoid trading into walls.
- Risk: Net Credit Tracker with Trailing Stop (BE at 25%, Trail at 40%).
- Constraints: 09:30-14:30 Entry, Max 1 trade per day.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np

# Line-buffered output (required for real-time log capture)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir) # openalgo/strategies
utils_dir = os.path.join(strategies_dir, "utils") # openalgo/strategies/utils
root_dir = os.path.dirname(strategies_dir) # openalgo

# CRITICAL: Insert root_dir BEFORE imports to allow 'from utils import ...' inside trading_utils
sys.path.insert(0, root_dir)
sys.path.insert(0, utils_dir)

try:
    from trading_utils import is_market_open, APIClient
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        safe_float,
        safe_int
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


# API Key retrieval
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


# ===========================
# CONFIGURATION
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftySmartMultiRegime")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Strategy Parameters
EMA_PERIOD = safe_int(os.getenv("EMA_PERIOD", "20"))
PCR_BULLISH = safe_float(os.getenv("PCR_BULLISH", "1.2"))
PCR_BEARISH = safe_float(os.getenv("PCR_BEARISH", "0.8"))
WALL_BUFFER = safe_float(os.getenv("WALL_BUFFER", "25.0")) # Points buffer from OI Walls

# Time Windows (IST)
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:30")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")

# Risk Parameters (Percentage of NET CREDIT)
SL_PCT = safe_float(os.getenv("SL_PCT", "40.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

# Rate Limiting
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1")) # Conservative
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Manual Expiry Override
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

def calculate_ema(series, period):
    """Calculate Exponential Moving Average using pandas."""
    return series.ewm(span=period, adjust=False).mean()

class NetCreditTracker(OptionPositionTracker):
    """
    Tracks PnL based on Net Credit collected.
    Implements Trailing Stop logic.
    """
    def __init__(self, sl_pct, tp_pct, max_hold_min):
        super().__init__(sl_pct, tp_pct, max_hold_min)
        self.trailing_sl_pct = -sl_pct # Initialize with hard SL (negative value)
        self.max_pnl_pct = 0.0

    def add_legs(self, legs, entry_prices, side="SELL"):
        super().add_legs(legs, entry_prices, side)
        if not hasattr(self, 'entry_time') or not self.entry_time:
            self.entry_time = datetime.now()

        # Reset trailing state
        self.trailing_sl_pct = -self.sl_pct
        self.max_pnl_pct = 0.0

    def should_exit(self, chain):
        if not self.open_legs:
            return False, [], ""

        # 1. Time Stop
        if getattr(self, 'entry_time', None):
            minutes_held = (datetime.now() - self.entry_time).total_seconds() / 60
            if minutes_held >= self.max_hold_min:
                return True, self.open_legs, f"time_stop ({int(minutes_held)}m)"

        # 2. Net Credit PnL Check
        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        net_credit_collected = 0.0
        current_cost_to_close = 0.0

        for leg in self.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            curr = ltp_map.get(sym, entry) # Fallback to entry
            action = leg["action"].upper()
            qty = safe_int(leg.get("quantity", 1))

            if action == "SELL":
                net_credit_collected += (entry * qty)
                current_cost_to_close += (curr * qty)
            else: # BUY (Hedges)
                net_credit_collected -= (entry * qty)
                current_cost_to_close -= (curr * qty)

        # Avoid division by zero
        if abs(net_credit_collected) < 0.01:
            return False, [], ""

        # PnL = (Credit Kept) - (Current Cost)
        pnl = net_credit_collected - current_cost_to_close

        # PnL % relative to Max Potential Profit (Net Credit)
        pnl_pct = (pnl / abs(net_credit_collected)) * 100

        # Update Max PnL
        if pnl_pct > self.max_pnl_pct:
            self.max_pnl_pct = pnl_pct

        # Trailing Logic
        # If PnL > 25%, Move SL to Break Even (0%)
        if self.max_pnl_pct >= 25.0 and self.trailing_sl_pct < 0.0:
            self.trailing_sl_pct = 0.0 # Break Even

        # If PnL > 40%, Move SL to +20%
        if self.max_pnl_pct >= 40.0 and self.trailing_sl_pct < 20.0:
            self.trailing_sl_pct = 20.0

        # Check Trailing SL
        if pnl_pct <= self.trailing_sl_pct:
             return True, self.open_legs, f"trailing_stop ({pnl_pct:.1f}% <= {self.trailing_sl_pct}%)"

        # Check Hard TP (Target)
        if pnl_pct >= self.tp_pct:
            return True, self.open_legs, f"take_profit ({pnl_pct:.1f}%)"

        return False, [], ""


class NiftySmartMultiRegime:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST) # For history
        self.tracker = NetCreditTracker(
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
        self.entered_today = False
        self.current_date = datetime.now().date()

        # EMA Cache
        self.last_ema_fetch = 0
        self.current_ema = 0.0

    def ensure_expiry(self):
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
                    self.logger.warning("No valid future expiry found.")
            else:
                self.logger.error(f"Failed to fetch expiry: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Expiry fetch error: {e}")

    def update_ema(self):
        if time.time() - self.last_ema_fetch < 300 and self.current_ema > 0:
            return

        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=5) # 5 days history for EMA(20) on 5m

            df = self.api_client.history(
                symbol=UNDERLYING,
                exchange=UNDERLYING_EXCHANGE,
                interval="5m",
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )

            if not df.empty and len(df) > EMA_PERIOD:
                df['ema'] = calculate_ema(df['close'], period=EMA_PERIOD)
                self.current_ema = df['ema'].iloc[-1]
                self.last_ema_fetch = time.time()
                self.logger.debug(f"Updated EMA({EMA_PERIOD}): {self.current_ema:.2f}")
            else:
                self.logger.warning("Insufficient history data for EMA calculation.")
        except Exception as e:
            self.logger.error(f"EMA calculation error: {e}")

    def analyze_chain(self, chain):
        """Analyze chain for PCR and OI Walls."""
        total_ce_oi = 0
        total_pe_oi = 0
        max_ce_oi = 0
        max_pe_oi = 0
        max_ce_strike = 0
        max_pe_strike = 0

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

        pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 1.0

        return {
            "pcr": pcr,
            "res_strike": max_ce_strike,
            "sup_strike": max_pe_strike
        }

    def determine_regime(self, pcr, spot):
        if self.current_ema <= 0:
            return "UNKNOWN"

        ema_bullish = spot > self.current_ema
        ema_bearish = spot < self.current_ema

        if pcr > PCR_BULLISH and ema_bullish:
            return "BULLISH"
        elif pcr < PCR_BEARISH and ema_bearish:
            return "BEARISH"

        return "NEUTRAL"

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position. Reason: {reason}")
        if not self.tracker.open_legs:
            return

        legs_to_close = []
        for leg in self.tracker.open_legs:
            close_leg = {
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": "BUY" if leg["action"] == "SELL" else "SELL",
                "quantity": leg["quantity"],
                "product": leg.get("product", PRODUCT)
            }
            legs_to_close.append(close_leg)

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
            else:
                self.logger.error(f"Exit failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _open_position(self, chain, regime, reason):
        self.logger.info(f"Attempting to open {regime} position ({reason})...")

        legs_config = []
        if regime == "NEUTRAL":
            legs_config = [
                {"offset": "OTM4", "option_type": "CE", "action": "BUY"},
                {"offset": "OTM4", "option_type": "PE", "action": "BUY"},
                {"offset": "OTM2", "option_type": "CE", "action": "SELL"},
                {"offset": "OTM2", "option_type": "PE", "action": "SELL"},
            ]
        elif regime == "BULLISH":
            legs_config = [
                {"offset": "OTM4", "option_type": "PE", "action": "BUY"},
                {"offset": "OTM2", "option_type": "PE", "action": "SELL"},
            ]
        elif regime == "BEARISH":
            legs_config = [
                {"offset": "OTM4", "option_type": "CE", "action": "BUY"},
                {"offset": "OTM2", "option_type": "CE", "action": "SELL"},
            ]

        resolved_legs = []
        api_legs = []

        for cfg in legs_config:
            offset = cfg["offset"]
            otype = cfg["option_type"].lower()

            found_item = None
            for item in chain:
                opt = item.get(otype, {})
                if opt.get("label") == offset:
                    found_item = opt
                    break

            # Fallback
            if not found_item and offset == "OTM4":
                 for item in chain:
                    opt = item.get(otype, {})
                    if opt.get("label") == "OTM3":
                        found_item = opt
                        break

            if found_item:
                symbol = found_item.get("symbol")
                ltp = safe_float(found_item.get("ltp"))

                api_legs.append({
                    "symbol": symbol,
                    "option_type": cfg["option_type"],
                    "action": cfg["action"],
                    "quantity": QUANTITY,
                    "product": PRODUCT
                })

                resolved_legs.append({
                    "symbol": symbol,
                    "option_type": cfg["option_type"],
                    "action": cfg["action"],
                    "quantity": QUANTITY,
                    "entry_price": ltp,
                    "product": PRODUCT
                })
            else:
                self.logger.warning(f"Could not resolve {offset} {cfg['option_type']}")
                return

        if len(resolved_legs) != len(legs_config):
            self.logger.error("Failed to resolve all required legs.")
            return

        api_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

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
                entry_prices = [leg["entry_price"] for leg in resolved_legs]
                self.tracker.add_legs(resolved_legs, entry_prices, side="SELL")
                self.entered_today = True
                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING}")

        while True:
            try:
                # 0. Daily Reset
                if datetime.now().date() != self.current_date:
                    self.entered_today = False
                    self.current_date = datetime.now().date()
                    self.limiter = TradeLimiter(
                        max_per_day=MAX_ORDERS_PER_DAY,
                        max_per_hour=MAX_ORDERS_PER_HOUR,
                        cooldown_seconds=COOLDOWN_SECONDS
                    )

                # 1. Market Hours
                if not is_market_open():
                    time.sleep(60)
                    continue

                # 2. Expiry
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Data
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
                self.update_ema()

                # 4. Exit
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Exit
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    eod_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
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
                            ema=f"{self.current_ema:.2f}",
                            max_pnl=f"{self.tracker.max_pnl_pct:.1f}%",
                            tsl=f"{self.tracker.trailing_sl_pct:.1f}%",
                            pos="OPEN"
                        ))

                # 5. Entry
                if not self.tracker.open_legs and not self.entered_today:
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    start_time_dt = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
                    end_time_dt = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()

                    if start_time_dt <= now.time() <= end_time_dt:
                        if self.limiter.allow():
                            stats = self.analyze_chain(chain)
                            pcr = stats["pcr"]
                            regime = self.determine_regime(pcr, underlying_ltp)

                            # OI Wall Filters
                            # Don't buy if spot is right below resistance (Bear Call is OK, Bull Put is dangerous)
                            # Don't sell if spot is right above support (Bull Put is OK, Bear Call is dangerous)

                            res_strike = stats["res_strike"]
                            sup_strike = stats["sup_strike"]

                            safe_bullish = underlying_ltp < (res_strike - WALL_BUFFER)
                            safe_bearish = underlying_ltp > (sup_strike + WALL_BUFFER)

                            should_enter = False

                            if regime == "BULLISH" and safe_bullish:
                                should_enter = True
                            elif regime == "BEARISH" and safe_bearish:
                                should_enter = True
                            elif regime == "NEUTRAL" and safe_bullish and safe_bearish:
                                should_enter = True

                            self.logger.info(format_kv(
                                spot=f"{underlying_ltp:.2f}",
                                ema=f"{self.current_ema:.2f}",
                                pcr=f"{pcr:.2f}",
                                regime=regime,
                                res=res_strike,
                                sup=sup_strike,
                                enter=should_enter
                            ))

                            if self.debouncer.edge("entry_signal", should_enter):
                                self._open_position(chain, regime, f"regime_{regime}_pcr_{pcr:.2f}")

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftySmartMultiRegime()
    strategy.run()
