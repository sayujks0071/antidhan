#!/usr/bin/env python3
"""
MCX Crude Oil Trend Strategy
MCX Commodity trading strategy with EMA, RSI, and ATR analysis
"""
import os
import sys
import logging
import argparse
import pandas as pd
from datetime import datetime, timedelta

# Add repo root to path
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(current_dir)
    utils_dir = os.path.join(strategies_dir, "utils")
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    openalgo_root = os.path.dirname(strategies_dir)
    if openalgo_root not in sys.path:
        sys.path.insert(0, openalgo_root)
except Exception:
    pass

try:
    from base_strategy import BaseStrategy
    from trading_utils import is_market_open
except ImportError:
    try:
        from utils.base_strategy import BaseStrategy
        from utils.trading_utils import is_market_open
    except ImportError:
        from openalgo.strategies.utils.base_strategy import BaseStrategy
        from openalgo.strategies.utils.trading_utils import is_market_open

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MCX_CrudeOil_Trend")

class MCXStrategy(BaseStrategy):
    def setup(self):
        """Initialize parameters"""
        # Default Parameters if not provided
        self.period_rsi = int(getattr(self, "period_rsi", 14))
        self.period_atr = int(getattr(self, "period_atr", 14))
        self.period_ema = int(getattr(self, "period_ema", 20))

        # Multi-Factor Parameters
        self.usd_inr_trend = getattr(self, "usd_inr_trend", "Neutral")
        self.usd_inr_volatility = float(getattr(self, "usd_inr_volatility", 0.0))
        self.seasonality_score = int(getattr(self, "seasonality_score", 50))
        self.global_alignment_score = int(getattr(self, "global_alignment_score", 50))

        self.data = pd.DataFrame()

        logger.info(f"Initialized Strategy for {self.symbol}")
        logger.info(f"Filters: Seasonality={self.seasonality_score}, USD_Vol={self.usd_inr_volatility}")

    def calculate_indicators(self, df):
        """Calculate technical indicators using BaseStrategy methods"""
        if df.empty:
            return df

        # Calculate indicators using BaseStrategy/trading_utils methods
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
        df["atr"] = self.calculate_atr_series(df, period=self.period_atr)
        df["ema_fast"] = self.calculate_ema(df["close"], period=self.period_ema)

        return df

    def check_signals(self, df):
        """Check entry and exit conditions"""
        if df.empty or len(df) < 50:
            return

        current = df.iloc[-1]

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        base_qty = 1
        if self.pm:
            # Use Adaptive Sizing (Monthly ATR favored)
            try:
                base_qty = self.pm.calculate_adaptive_quantity(
                    capital=500000,
                    risk_per_trade_pct=1.0,
                    atr=current["atr"],
                    price=current["close"],
                    client=self.client,
                    exchange="MCX"
                )
                logger.info(f"Adaptive Quantity Calculated: {base_qty}")
            except Exception as e:
                logger.error(f"Adaptive sizing failed: {e}. Defaulting to 1.")
                base_qty = 1

        if usd_vol_high:
            logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7)) # Valid only if base > 1, but keeps logic

        if not seasonality_ok and not has_position:
            logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic
        # Buy: Close > EMA AND RSI > 50
        buy_signal = (current["close"] > current["ema_fast"]) and (current["rsi"] > 50)
        # Sell: Close < EMA AND RSI < 50
        sell_signal = (current["close"] < current["ema_fast"]) and (current["rsi"] < 50)

        if not has_position:
            if buy_signal:
                logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.buy(base_qty, current["close"])
            elif sell_signal:
                logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.sell(base_qty, current["close"])

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price
            atr_val = current["atr"]

            # Target/Stop
            target = 2.0 * atr_val
            stop = 1.0 * atr_val

            exit_signal = False
            reason = ""

            if pos_qty > 0: # Long
                if (current["close"] >= entry_price + target):
                    exit_signal = True
                    reason = "Target Hit"
                elif (current["close"] <= entry_price - stop):
                    exit_signal = True
                    reason = "Stop Loss Hit"
                elif (current["close"] < current["ema_fast"]): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"

                if exit_signal:
                    logger.info(f"EXIT LONG: {reason}")
                    self.sell(abs(pos_qty), current["close"])

            elif pos_qty < 0: # Short
                if (current["close"] <= entry_price - target):
                    exit_signal = True
                    reason = "Target Hit"
                elif (current["close"] >= entry_price + stop):
                    exit_signal = True
                    reason = "Stop Loss Hit"
                elif (current["close"] > current["ema_fast"]): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"

                if exit_signal:
                    logger.info(f"EXIT SHORT: {reason}")
                    self.buy(abs(pos_qty), current["close"])

    def cycle(self):
        """Main execution logic"""
        # Fetch Data
        df = self.fetch_history(days=5, interval="15m")
        if df.empty or len(df) < 50:
            logger.warning(f"Insufficient data for {self.symbol}.")
            return

        df = self.calculate_indicators(df)
        self.check_signals(df)

    def generate_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        df = self.calculate_indicators(df)
        if df.empty or len(df) < 50:
             return "HOLD", 0.0, {}

        current = df.iloc[-1]

        buy_signal = (current["close"] > current["ema_fast"]) and (current["rsi"] > 50)
        sell_signal = (current["close"] < current["ema_fast"]) and (current["rsi"] < 50)

        if buy_signal:
            return "BUY", 1.0, {"reason": "Trend Long"}
        elif sell_signal:
            return "SELL", 1.0, {"reason": "Trend Short"}

        return "HOLD", 0.0, {}


# Backtesting support
# Replaced with standard BaseStrategy wrapper
generate_signal = MCXStrategy.backtest_signal

if __name__ == "__main__":
    parser = MCXStrategy.get_standard_parser("MCX Crude Oil Trend Strategy")
    # Multi-Factor Arguments
    parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
    parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
    parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
    parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
    parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
    parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
    parser.add_argument("--period_ema", type=int, default=20, help="EMA Period")

    MCXStrategy.add_arguments = lambda parser: None # Arguments already added above manually for this script style

    # We can use the BaseStrategy CLI but we need to inject the specific parser
    # Or just replicate the main block

    args = parser.parse_args()
    kwargs = MCXStrategy.parse_arguments(args)

    if not kwargs.get('symbol'):
         print("Error: Must provide --symbol (or --underlying if supported)")
         sys.exit(1)

    try:
         strategy = MCXStrategy(**kwargs)
         strategy.run()
    except Exception as e:
         print(f"Error: {e}")
         import traceback
         traceback.print_exc()
