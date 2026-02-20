#!/usr/bin/env python3
"""
[Nifty Adaptive Trend] - NIFTY Options (OpenAlgo Web UI Compatible)
Adaptive Nifty strategy using EMA trend following and PCR confirmation to deploy Credit Spreads or Iron Condors.
"""
import os
import sys
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

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
    import traceback
    traceback.print_exc()
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)

# API Key retrieval
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


class NiftyAdaptiveTrendStrategy:
    """
    Adaptive Nifty Strategy:
    - Bullish: Price > EMA(20) & PCR > 1.0 -> Bull Put Spread
    - Bearish: Price < EMA(20) & PCR < 0.8 -> Bear Call Spread
    - Neutral: Price near EMA(20) & PCR 0.8-1.0 -> Iron Condor
    """
    def __init__(self):
        self.logger = PrintLogger()
        self.api_key = API_KEY
        self.host = HOST

        # Configuration
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1")) # Multiplier for lot size
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Parameters
        self.sl_pct = float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Loop Control
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # Clients
        self.client = OptionChainClient(api_key=self.api_key, host=self.host)
        self.api_client = APIClient(api_key=self.api_key, host=self.host)

        # Trackers
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=int(os.getenv("MAX_ORDERS_PER_DAY", "5")),
            max_per_hour=int(os.getenv("MAX_ORDERS_PER_HOUR", "2")),
            cooldown_seconds=int(os.getenv("COOLDOWN_SECONDS", "120"))
        )
        self.debouncer = SignalDebouncer()

        # State
        self.expiry = None
        self.last_expiry_check = 0

    def ensure_expiry(self):
        if not self.expiry or (time.time() - self.last_expiry_check > self.expiry_refresh_sec):
            try:
                # Prefer manual override
                manual_expiry = os.getenv("EXPIRY_DATE")
                if manual_expiry:
                    self.expiry = manual_expiry
                    self.logger.info(f"Using manual expiry: {self.expiry}")
                else:
                    res = self.client.expiry(self.underlying, self.options_exchange)
                    if res.get("status") == "success":
                        dates = res.get("data", [])
                        self.expiry = choose_nearest_expiry(dates)
                        self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                    else:
                        self.logger.warning("Failed to fetch expiry dates")

                self.last_expiry_check = time.time()
            except Exception as e:
                self.logger.error(f"Error resolving expiry: {e}")

    def calculate_indicators(self):
        """Fetch history and calculate EMA(20)."""
        try:
            # Fetch last 2 days of 5m data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=5)

            df = self.api_client.history(
                symbol=self.underlying,
                exchange=self.underlying_exchange,
                interval="5m",
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )

            if df.empty:
                return None, 0.0

            # Calculate EMA 20
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()

            last_row = df.iloc[-1]
            return last_row, df

        except Exception as e:
            self.logger.error(f"Indicator calculation error: {e}")
            return None, 0.0

    def calculate_pcr(self, chain):
        total_ce_oi = 0
        total_pe_oi = 0

        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            total_ce_oi += safe_int(ce.get("oi", 0))
            total_pe_oi += safe_int(pe.get("oi", 0))

        if total_ce_oi == 0:
            return 0.0

        return total_pe_oi / total_ce_oi

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position. Reason: {reason}")

        legs_to_close = []
        for leg in self.tracker.open_legs:
            # Reverse action
            exit_action = "BUY" if leg["action"] == "SELL" else "SELL"
            legs_to_close.append({
                "symbol": leg["symbol"],
                "action": exit_action,
                "quantity": leg["quantity"],
                "product": self.product,
                "option_type": leg.get("option_type", "CE")
            })

        for leg in legs_to_close:
             self.client.placesmartorder(
                 strategy="NiftyAdaptiveTrend_Exit",
                 symbol=leg["symbol"],
                 action=leg["action"],
                 exchange=self.options_exchange,
                 pricetype="MARKET",
                 product=self.product,
                 quantity=leg["quantity"],
                 position_size=leg["quantity"]
             )

        self.tracker.clear()
        self.logger.info("Position closed (orders placed).")

    def run(self):
        self.logger.info("Strategy Started: Nifty Adaptive Trend")

        while True:
            try:
                # 1. Market Open Check
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # Fetch Chain
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # 2. EOD Square-off (3:15 PM)
                now = datetime.now()
                if now.time() >= datetime.strptime("15:15", "%H:%M").time():
                    if self.tracker.open_legs:
                        self._close_position(chain, "EOD Square-off")
                    time.sleep(60)
                    continue

                # 3. Exit Logic (SL/TP/Time)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # 4. Entry Time Filter (09:30 - 14:30)
                if now.time() < datetime.strptime("09:30", "%H:%M").time() or \
                   now.time() > datetime.strptime("14:30", "%H:%M").time():
                    time.sleep(self.sleep_seconds)
                    continue

                # Calculate Indicators
                last_candle, df = self.calculate_indicators()
                if last_candle is None:
                    self.logger.warning("Insufficient history data")
                    time.sleep(self.sleep_seconds)
                    continue

                spot_price = safe_float(last_candle['close'])
                ema20 = safe_float(last_candle['ema20'])
                pcr = self.calculate_pcr(chain)

                # Log Status
                self.logger.info(format_kv(
                    spot=f"{spot_price:.2f}",
                    ema=f"{ema20:.2f}",
                    pcr=f"{pcr:.2f}",
                    expiry=self.expiry
                ))

                # Entry Logic
                if not self.tracker.open_legs and self.limiter.allow():

                    signal = None
                    strategy_legs = []

                    # 1. Bullish Regime
                    if spot_price > ema20 and pcr > 1.0:
                        if self.debouncer.edge("bullish_signal", True):
                            signal = "BULLISH"
                            # Bull Put Spread: Sell OTM1 PE, Buy OTM3 PE
                            strategy_legs = [
                                {"offset": "OTM1", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM3", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product}
                            ]

                    # 2. Bearish Regime
                    elif spot_price < ema20 and pcr < 0.8:
                        if self.debouncer.edge("bearish_signal", True):
                            signal = "BEARISH"
                            # Bear Call Spread: Sell OTM1 CE, Buy OTM3 CE
                            strategy_legs = [
                                {"offset": "OTM1", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM3", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product}
                            ]

                    # 3. Neutral Regime (Iron Condor)
                    # Price close to EMA (within 0.2%) and PCR Neutral
                    elif abs(spot_price - ema20) / ema20 < 0.002 and 0.8 <= pcr <= 1.0:
                         if self.debouncer.edge("neutral_signal", True):
                            signal = "NEUTRAL"
                            # Iron Condor: Sell OTM2 CE/PE, Buy OTM4 CE/PE
                            strategy_legs = [
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product}
                            ]

                    if signal and strategy_legs:
                        self.logger.info(f"Trade Signal: {signal}")

                        # Place Order
                        resp = self.client.optionsmultiorder(
                            strategy="NiftyAdaptiveTrend",
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=strategy_legs
                        )

                        if resp.get("status") == "success":
                            self.limiter.record()
                            self.logger.info(f"Order Placed: {resp.get('message')}")

                            # Resolve symbols to initialize tracker
                            resolved_legs = []
                            atm_strike = 0
                            for item in chain:
                                if item.get("ce", {}).get("label") == "ATM":
                                    atm_strike = item["strike"]
                                    break

                            # Sort chain by strike
                            sorted_chain = sorted(chain, key=lambda x: x["strike"])
                            atm_index = -1
                            for i, item in enumerate(sorted_chain):
                                if item["strike"] == atm_strike:
                                    atm_index = i
                                    break

                            if atm_index != -1:
                                for leg in strategy_legs:
                                    offset = leg["offset"]
                                    otype = leg["option_type"]

                                    # Parse offset
                                    target_index = atm_index
                                    if offset == "ATM":
                                        pass
                                    elif offset.startswith("OTM"):
                                        n = int(offset.replace("OTM", ""))
                                        if otype == "CE": target_index += n
                                        else: target_index -= n
                                    elif offset.startswith("ITM"):
                                        n = int(offset.replace("ITM", ""))
                                        if otype == "CE": target_index -= n
                                        else: target_index += n

                                    if 0 <= target_index < len(sorted_chain):
                                        item = sorted_chain[target_index]
                                        opt = item.get(otype.lower(), {})
                                        symbol = opt.get("symbol")
                                        ltp = safe_float(opt.get("ltp"))
                                        if symbol:
                                            resolved_legs.append({
                                                "symbol": symbol,
                                                "action": leg["action"],
                                                "quantity": leg["quantity"],
                                                "entry_price": ltp,
                                                "option_type": otype
                                            })

                            if resolved_legs:
                                entry_prices = [leg["entry_price"] for leg in resolved_legs]
                                self.tracker.add_legs(resolved_legs, entry_prices, side="SELL") # Mostly Credit Strategies
                                self.logger.info(f"Tracker initialized with {len(resolved_legs)} legs.")
                        else:
                            self.logger.error(f"Order Failed: {resp.get('message')}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                # traceback.print_exc()

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    strategy = NiftyAdaptiveTrendStrategy()
    strategy.run()
