#!/usr/bin/env python3
"""
[Nifty Smart Trend OI] - NIFTY Options (OpenAlgo Web UI Compatible)
Combines EMA Trend Following with PCR Sentiment to trade Credit Spreads or Iron Condors.
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
    print("CRITICAL: API Key must be set in OPENALGO_APIKEY environment variable", flush=True)


# ===========================
# CONFIGURATION
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftySmartTrendOI")
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
MIN_STRADDLE_PREMIUM = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "80.0"))

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
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "2"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "5"))

# Manual Expiry Override
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

def calculate_ema(series, period):
    """Calculate Exponential Moving Average using pandas."""
    return series.ewm(span=period, adjust=False).mean()

class NetCreditTracker(OptionPositionTracker):
    """
    Custom Position Tracker for Credit Strategies.
    Calculates PnL based on Net Credit Collected.
    """
    def add_legs(self, legs, entry_prices, side="SELL"):
        """Override to ensure entry time is tracked."""
        super().add_legs(legs, entry_prices, side)
        if not hasattr(self, 'entry_time') or not self.entry_time:
            self.entry_time = datetime.now()

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
        # If cost > credit, PnL is negative.
        pnl = net_credit_collected - current_cost_to_close

        # PnL % relative to Max Potential Profit (Net Credit)
        pnl_pct = (pnl / abs(net_credit_collected)) * 100

        # Check SL (e.g. -40%)
        if pnl_pct <= -self.sl_pct:
            return True, self.open_legs, f"stop_loss ({pnl_pct:.1f}%)"

        # Check TP (e.g. +50%)
        if pnl_pct >= self.tp_pct:
            return True, self.open_legs, f"take_profit ({pnl_pct:.1f}%)"

        return False, [], ""


class NiftySmartTrendOIStrategy:
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
        """Refresh expiry date if needed."""
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
        """Fetch history and calculate EMA."""
        # Update every 5 minutes or so
        if time.time() - self.last_ema_fetch < 300 and self.current_ema > 0:
            return

        try:
            # Fetch last 2 days of 5m data to ensure enough for EMA(20)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=5)

            df = self.api_client.history(
                symbol=UNDERLYING,
                exchange=UNDERLYING_EXCHANGE,
                interval="5m",
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )

            if not df.empty and len(df) > EMA_PERIOD:
                # Calculate EMA
                # Note: APIClient returns 'close' column
                df['ema'] = calculate_ema(df['close'], period=EMA_PERIOD)
                self.current_ema = df['ema'].iloc[-1]
                self.last_ema_fetch = time.time()
                self.logger.debug(f"Updated EMA({EMA_PERIOD}): {self.current_ema:.2f}")
            else:
                self.logger.warning("Insufficient history data for EMA calculation.")
        except Exception as e:
            self.logger.error(f"EMA calculation error: {e}")

    def calculate_pcr(self, chain):
        """Calculate Put-Call Ratio from chain Open Interest."""
        total_ce_oi = 0
        total_pe_oi = 0
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            total_ce_oi += safe_int(ce.get("oi", 0))
            total_pe_oi += safe_int(pe.get("oi", 0))

        if total_ce_oi == 0:
            return 1.0 # Default neutral

        return total_pe_oi / total_ce_oi

    def determine_regime(self, pcr, spot):
        """
        Determine market regime based on PCR and Price vs EMA.
        """
        if self.current_ema <= 0:
            return "UNKNOWN"

        ema_bullish = spot > self.current_ema
        ema_bearish = spot < self.current_ema

        # Combine Signals
        if pcr > PCR_BULLISH and ema_bullish:
            return "BULLISH"
        elif pcr < PCR_BEARISH and ema_bearish:
            return "BEARISH"

        # Neutral Logic: PCR in middle range or Price very close to EMA
        # Or mixed signals (e.g. PCR Bullish but Price < EMA) -> Neutral/Sideways
        return "NEUTRAL"

    def _close_position(self, chain, reason):
        """Close all open legs."""
        self.logger.info(f"Closing position. Reason: {reason}")
        if not self.tracker.open_legs:
            return

        # Prepare exit legs (Reverse actions)
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

        # Sort: BUY actions (closing shorts) first
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
        """Open position based on regime."""
        self.logger.info(f"Attempting to open {regime} position ({reason})...")

        legs_config = []
        # Define legs based on regime
        if regime == "NEUTRAL":
            # Iron Condor: Sell OTM2 Strangle, Buy OTM4 Wings
            legs_config = [
                {"offset": "OTM4", "option_type": "CE", "action": "BUY"},
                {"offset": "OTM4", "option_type": "PE", "action": "BUY"},
                {"offset": "OTM2", "option_type": "CE", "action": "SELL"},
                {"offset": "OTM2", "option_type": "PE", "action": "SELL"},
            ]
        elif regime == "BULLISH":
            # Bull Put Spread: Sell OTM2 PE, Buy OTM4 PE
            legs_config = [
                {"offset": "OTM4", "option_type": "PE", "action": "BUY"},
                {"offset": "OTM2", "option_type": "PE", "action": "SELL"},
            ]
        elif regime == "BEARISH":
            # Bear Call Spread: Sell OTM2 CE, Buy OTM4 CE
            legs_config = [
                {"offset": "OTM4", "option_type": "CE", "action": "BUY"},
                {"offset": "OTM2", "option_type": "CE", "action": "SELL"},
            ]

        resolved_legs = []
        api_legs = []

        # Resolve symbols locally
        for cfg in legs_config:
            offset = cfg["offset"]
            otype = cfg["option_type"].lower()

            found_item = None
            # Find the item with the matching label
            for item in chain:
                opt = item.get(otype, {})
                if opt.get("label") == offset:
                    found_item = opt
                    break

            # Fallback logic if exact offset missing
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

        # Sort API legs: BUY first for margin benefit
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
                # Add to Tracker
                entry_prices = [leg["entry_price"] for leg in resolved_legs]
                self.tracker.add_legs(resolved_legs, entry_prices, side="SELL")

                self.entered_today = True
                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

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
                    ) # Reset limiter daily count

                # 1. Market Hours Check
                market_open = True
                try:
                    if not is_market_open():
                        market_open = False
                except:
                    pass

                if not market_open:
                    time.sleep(60)
                    continue

                # 2. Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch Data
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

                # Update EMA
                self.update_ema()

                # 4. Exit Management (Priority)
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
                        # Log status
                        pcr = self.calculate_pcr(chain)
                        self.logger.info(format_kv(
                            spot=f"{underlying_ltp:.2f}",
                            ema=f"{self.current_ema:.2f}",
                            pcr=f"{pcr:.2f}",
                            pos="OPEN",
                            pnl="RUNNING"
                        ))

                # 5. Entry Logic
                if not self.tracker.open_legs and not self.entered_today:
                    # Time Check
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    start_time_dt = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
                    end_time_dt = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()

                    if start_time_dt <= now.time() <= end_time_dt:
                        if self.limiter.allow():
                            # Calculate Indicators
                            pcr = self.calculate_pcr(chain)
                            regime = self.determine_regime(pcr, underlying_ltp)

                            # Straddle Premium Check
                            atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)
                            straddle_premium = 0.0
                            if atm_item:
                                ce_ltp = safe_float((atm_item.get("ce") or {}).get("ltp"))
                                pe_ltp = safe_float((atm_item.get("pe") or {}).get("ltp"))
                                straddle_premium = ce_ltp + pe_ltp

                            self.logger.info(format_kv(
                                spot=f"{underlying_ltp:.2f}",
                                ema=f"{self.current_ema:.2f}",
                                pcr=f"{pcr:.2f}",
                                regime=regime,
                                straddle=f"{straddle_premium:.2f}",
                                pos="FLAT"
                            ))

                            should_enter = (regime != "UNKNOWN") and (straddle_premium > MIN_STRADDLE_PREMIUM)

                            if self.debouncer.edge("entry_signal", should_enter):
                                self._open_position(chain, regime, f"regime_{regime}_pcr_{pcr:.2f}")

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftySmartTrendOIStrategy()
    strategy.run()
