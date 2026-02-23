#!/usr/bin/env python3
"""
[Nifty Smart Trend & OI Reversal] - NIFTY Options (OpenAlgo Web UI Compatible)
Combines EMA(20) Trend + PCR Sentiment for Regime Detection (Bull/Bear/Neutral).
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
    from trading_utils import is_market_open, APIClient, calculate_ema, calculate_atr
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
            print("Successfully retrieved API Key from database.", flush=True)
    except Exception as e:
        print(f"Warning: Could not retrieve API key from database: {e}", flush=True)

if not API_KEY:
    raise ValueError("API Key must be set in OPENALGO_APIKEY environment variable")

class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)

class NiftySmartTrendOIReversal:
    def __init__(self):
        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftySmartTrendOI")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Parameters
        self.sl_pct = float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Timing
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))

        # Limits
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "5"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

        # Clients & Trackers
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()
        self.logger = PrintLogger()

        # State
        self.expiry = os.getenv("EXPIRY_DATE")
        self.last_expiry_check = 0
        self.last_history_fetch = 0
        self.ema_value = 0.0
        self.regime = "NEUTRAL" # BULLISH, BEARISH, NEUTRAL

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            resp = self.client.expiry(self.underlying, self.options_exchange)
            if resp.get("status") == "success":
                dates = resp.get("data", [])
                self.expiry = choose_nearest_expiry(dates)
                self.logger.info(f"Updated Expiry: {self.expiry}")
            self.last_expiry_check = now

    def update_indicators(self):
        # Fetch history for EMA calculation every 5 minutes or if 0
        now = time.time()
        if self.ema_value == 0 or (now - self.last_history_fetch > 300):
            try:
                # 5-minute candles, last 200 bars
                end_date = datetime.now()
                start_date = end_date - timedelta(days=5) # Enough for 200 bars of 5m

                df = self.api_client.history(
                    symbol=self.underlying,
                    exchange=self.underlying_exchange,
                    interval="5m",
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d")
                )

                if not df.empty and len(df) > 20:
                    ema_series = calculate_ema(df["close"], period=20)
                    self.ema_value = ema_series.iloc[-1]
                    self.last_history_fetch = now
                    self.logger.info(f"Updated EMA(20): {self.ema_value:.2f}")
            except Exception as e:
                self.logger.error(f"Failed to update indicators: {e}")

    def calculate_pcr(self, chain):
        total_ce_oi = 0
        total_pe_oi = 0
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            total_ce_oi += safe_int(ce.get("oi", 0))
            total_pe_oi += safe_int(pe.get("oi", 0))

        if total_ce_oi > 0:
            return total_pe_oi / total_ce_oi
        return 1.0

    def determine_regime(self, spot, pcr):
        # Default Neutral
        regime = "NEUTRAL"

        if self.ema_value > 0:
            # Bullish: Price > EMA AND PCR > 1.2
            if spot > self.ema_value and pcr > 1.25:
                regime = "BULLISH"
            # Bearish: Price < EMA AND PCR < 0.8
            elif spot < self.ema_value and pcr < 0.75:
                regime = "BEARISH"

        return regime

    def get_legs(self, regime, chain, spot):
        legs = []
        strategy_type = ""

        # Find ATM Strike
        # Simple method: Closest strike to spot
        atm_strike = min(chain, key=lambda x: abs(x["strike"] - spot))["strike"]
        strike_diff = 50 # Assuming Nifty, can be dynamic
        if len(chain) > 1:
            strike_diff = abs(chain[1]["strike"] - chain[0]["strike"])

        # OTM2 and OTM4 offsets
        otm2_dist = 2 * strike_diff
        otm4_dist = 4 * strike_diff

        if regime == "BULLISH":
            # Bull Put Spread: Sell OTM2 PE, Buy OTM4 PE
            strategy_type = "Bull Put Spread"
            sell_strike = atm_strike - otm2_dist
            buy_strike = atm_strike - otm4_dist

            legs.append({"strike": sell_strike, "option_type": "PE", "action": "SELL", "offset": "OTM2"})
            legs.append({"strike": buy_strike, "option_type": "PE", "action": "BUY", "offset": "OTM4"})

        elif regime == "BEARISH":
            # Bear Call Spread: Sell OTM2 CE, Buy OTM4 CE
            strategy_type = "Bear Call Spread"
            sell_strike = atm_strike + otm2_dist
            buy_strike = atm_strike + otm4_dist

            legs.append({"strike": sell_strike, "option_type": "CE", "action": "SELL", "offset": "OTM2"})
            legs.append({"strike": buy_strike, "option_type": "CE", "action": "BUY", "offset": "OTM4"})

        else: # NEUTRAL
            # Iron Condor: Sell OTM2 CE/PE, Buy OTM4 CE/PE
            strategy_type = "Iron Condor"

            # Call side
            sell_ce = atm_strike + otm2_dist
            buy_ce = atm_strike + otm4_dist
            # Put side
            sell_pe = atm_strike - otm2_dist
            buy_pe = atm_strike - otm4_dist

            legs.append({"strike": sell_ce, "option_type": "CE", "action": "SELL", "offset": "OTM2"})
            legs.append({"strike": buy_ce, "option_type": "CE", "action": "BUY", "offset": "OTM4"})
            legs.append({"strike": sell_pe, "option_type": "PE", "action": "SELL", "offset": "OTM2"})
            legs.append({"strike": buy_pe, "option_type": "PE", "action": "BUY", "offset": "OTM4"})

        # Construct full leg objects for API
        api_legs = []
        for leg in legs:
            api_legs.append({
                "offset": leg["offset"],
                "option_type": leg["option_type"],
                "action": leg["action"],
                "quantity": self.quantity,
                "product": self.product
            })

        return api_legs, strategy_type

    def resolve_legs(self, offset_legs, chain, spot):
        # Helper to convert offset-based legs to specific symbols and prices from chain
        resolved = []

        # Find ATM
        atm_item = min(chain, key=lambda x: abs(x["strike"] - spot))
        atm_strike = atm_item["strike"]
        strike_diff = 50
        if len(chain) > 1:
            strike_diff = abs(chain[1]["strike"] - chain[0]["strike"])

        # Map offsets to strikes
        for leg in offset_legs:
            offset = leg["offset"] # e.g. "OTM2"
            otype = leg["option_type"] # "CE" or "PE"

            # Parse offset
            multiplier = 0
            if "ATM" in offset:
                multiplier = 0
            elif "OTM" in offset:
                multiplier = int(offset.replace("OTM", ""))

            target_strike = atm_strike
            if otype == "CE":
                target_strike = atm_strike + (multiplier * strike_diff)
            else:
                target_strike = atm_strike - (multiplier * strike_diff)

            # Find item in chain
            match = next((x for x in chain if abs(x["strike"] - target_strike) < 0.1), None)
            if match:
                opt_data = match.get(otype.lower(), {})
                resolved.append({
                    "symbol": opt_data.get("symbol"),
                    "action": leg["action"],
                    "quantity": leg["quantity"],
                    "entry_price": safe_float(opt_data.get("ltp")),
                    "strike": match["strike"],
                    "option_type": otype
                })

        return resolved

    def run(self):
        self.logger.info(f"Strategy {self.strategy_name} Started. Waiting for market...")

        while True:
            try:
                # 1. Market Hours Check
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                # 2. Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No Expiry found. Retrying...")
                    time.sleep(self.sleep_seconds)
                    continue

                # 3. Fetch Chain
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid Chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = safe_float(chain_resp.get("underlying_ltp", 0))

                # 4. Exit Management
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self.logger.info(f"Exit Triggered: {exit_reason}")
                        self.logger.info(format_kv(event="close_position", reason=exit_reason))
                        self.tracker.clear()

                    time.sleep(self.sleep_seconds)
                    continue

                # 5. Calculate Indicators
                self.update_indicators()
                pcr = self.calculate_pcr(chain)

                # 6. Determine Regime
                new_regime = self.determine_regime(spot, pcr)

                # Log status
                self.logger.info(format_kv(
                    spot=spot,
                    ema=f"{self.ema_value:.2f}",
                    pcr=f"{pcr:.2f}",
                    regime=new_regime
                ))

                # 7. Entry Logic
                if self.limiter.allow():
                    legs, strategy_type = self.get_legs(new_regime, chain, spot)

                    if legs:
                        self.logger.info(f"Attempting Entry: {strategy_type} ({new_regime})")

                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=legs
                        )

                        if resp.get("status") == "success":
                            self.logger.info(format_kv(event="trade", action="OPEN", strategy=strategy_type))
                            self.limiter.record()

                            resolved_legs = self.resolve_legs(legs, chain, spot)
                            entry_prices = [leg["entry_price"] for leg in resolved_legs]

                            self.tracker.add_legs(resolved_legs, entry_prices, side="SELL")
                        else:
                            self.logger.error(f"Order Failed: {resp.get('message')}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                time.sleep(self.sleep_seconds)

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftySmartTrendOIReversal().run()
