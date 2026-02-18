#!/usr/bin/env python3
"""
MCX Gold Trend Strategy
MCX Commodity trading strategy with SMA (20/50), RSI, and ADX analysis
Inherits from BaseStrategy for consistent infrastructure usage.
"""
import os
import sys
import logging
import pandas as pd
from datetime import datetime, timedelta

# Add repo root to path
try:
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, "utils")
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol

class MCXGoldTrendStrategy(BaseStrategy):
    def setup(self):
        # Default Parameters
        self.period_rsi = getattr(self, "period_rsi", 14)
        self.period_atr = getattr(self, "period_atr", 14)
        self.period_sma_fast = getattr(self, "period_sma_fast", 20)
        self.period_sma_slow = getattr(self, "period_sma_slow", 50)
        self.period_adx = getattr(self, "period_adx", 14)

        # Multi-Factor Parameters
        self.seasonality_score = getattr(self, "seasonality_score", 50)
        self.usd_inr_volatility = getattr(self, "usd_inr_volatility", 0.0)
        self.global_alignment_score = getattr(self, "global_alignment_score", 50)

    def cycle(self):
        """
        Main Strategy Logic Execution Cycle
        """
        # Fetch Data using BaseStrategy's robust method
        # MCX typically uses 15m or 1h. Defaulting to 15m as per original script.
        df = self.fetch_history(days=5, interval="15m", exchange="MCX")

        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}.")
            return

        # Calculate Indicators
        df['rsi'] = self.calculate_rsi(df['close'], self.period_rsi)
        df['atr'] = self.calculate_atr_series(df, self.period_atr) # Series needed for targets
        df['sma_fast'] = self.calculate_sma(df['close'], self.period_sma_fast)
        df['sma_slow'] = self.calculate_sma(df['close'], self.period_sma_slow)
        df['adx'] = self.calculate_adx_series(df, self.period_adx)

        current = df.iloc[-1]

        # Position Management
        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic
        buy_signal = (current["sma_fast"] > current["sma_slow"]) and (current["rsi"] > 50) and (current["adx"] > 25)
        sell_signal = (current["sma_fast"] < current["sma_slow"]) and (current["rsi"] < 50) and (current["adx"] > 25)

        if not has_position:
            if buy_signal or sell_signal:
                # Adaptive Sizing using Monthly ATR via BaseStrategy
                qty = self.get_adaptive_quantity(current['close'], risk_pct=1.0, capital=500000)

                # Apply modifier for USD Volatility
                if usd_vol_high:
                    self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
                    qty = max(1, int(qty * 0.7))

                action = "BUY" if buy_signal else "SELL"
                self.logger.info(f"{action} SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                self.execute_trade(action, qty, current['close'])

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
                elif (current["sma_fast"] < current["sma_slow"]): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"
            elif pos_qty < 0: # Short
                if (current["close"] <= entry_price - target):
                    exit_signal = True
                    reason = "Target Hit"
                elif (current["close"] >= entry_price + stop):
                    exit_signal = True
                    reason = "Stop Loss Hit"
                elif (current["sma_fast"] > current["sma_slow"]): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"

            if exit_signal:
                self.logger.info(f"EXIT: {reason}")
                action = "SELL" if pos_qty > 0 else "BUY"
                self.execute_trade(action, abs(pos_qty), current["close"])

    def get_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        # Use helper methods to calculate indicators on the fly
        df['rsi'] = self.calculate_rsi(df['close'], self.period_rsi)
        df['sma_fast'] = self.calculate_sma(df['close'], self.period_sma_fast)
        df['sma_slow'] = self.calculate_sma(df['close'], self.period_sma_slow)
        df['adx'] = self.calculate_adx_series(df, self.period_adx)

        current = df.iloc[-1]

        buy_signal = (current["sma_fast"] > current["sma_slow"]) and (current["rsi"] > 50) and (current["adx"] > 25)
        sell_signal = (current["sma_fast"] < current["sma_slow"]) and (current["rsi"] < 50) and (current["adx"] > 25)

        if buy_signal:
            return "BUY", 1.0, {"reason": "Trend Long"}
        elif sell_signal:
            return "SELL", 1.0, {"reason": "Trend Short"}

        return "HOLD", 0.0, {}

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")

if __name__ == "__main__":
    MCXGoldTrendStrategy.cli()
