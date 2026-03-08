#!/usr/bin/env python3
"""
[Strategy Description]
MCX Smart Breakout Strategy V2 (Alpha V2)
Innovative volatility-adjusted breakout strategy with dynamic risk management.
Uses Bollinger Bands Squeeze/Expansion logic and ATR-based exits.
Enhancements:
- Inherits from BaseStrategy (DRY).
- ADX Filter (> 25) for Trend Strength.
- Trailing Stop (Trail SMA 20).
"""
import os
import sys
import argparse
import pandas as pd
import numpy as np

# Add repo root to path
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(current_dir)
    utils_dir = os.path.join(strategies_dir, "utils")
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
except Exception:
    pass

try:
    from base_strategy import BaseStrategy
except ImportError:
    try:
        from utils.base_strategy import BaseStrategy
    except ImportError:
        from openalgo.strategies.utils.base_strategy import BaseStrategy

class MCXSmartStrategyV2(BaseStrategy):
    def setup(self):
        # Default Parameters if not provided
        self.period_rsi = getattr(self, "period_rsi", 14)
        self.period_atr = getattr(self, "period_atr", 14)
        self.adx_threshold = getattr(self, "adx_threshold", 25) # New Feature

    def calculate_indicators(self, df):
        """Calculate technical indicators using BaseStrategy helpers."""
        # SMA 50 for Trend Filter
        df['sma_50'] = self.calculate_sma(df['close'], period=50)

        # SMA 20 (BB Mid) for Trailing Stop
        df['sma_20'] = self.calculate_sma(df['close'], period=20)

        # RSI 14
        df['rsi'] = self.calculate_rsi(df['close'], period=self.period_rsi)

        # Bollinger Bands (20, 2)
        df['bb_mid'], df['bb_upper'], df['bb_lower'] = self.calculate_bollinger_bands(df['close'], window=20, num_std=2)

        # ATR 14
        df['atr'] = self.calculate_atr_series(df, period=self.period_atr)

        # ATR Moving Average (Volatility Expansion Check)
        df['atr_ma'] = self.calculate_sma(df['atr'], period=10)

        # ADX 14 (New Feature)
        df['adx'] = self.calculate_adx_series(df, period=14)

        return df

    def cycle(self):
        """Main execution logic for live trading."""
        # Fetch Data
        df = self.fetch_history(days=5, interval="15m") # 15m default
        if df.empty or len(df) < 50:
            self.logger.warning("Insufficient data.")
            return

        df = self.calculate_indicators(df)
        self.check_signals(df)

    def check_signals(self, df):
        """Check entry and exit conditions."""
        current = df.iloc[-1]

        # Position State
        has_position = False
        pos_qty = 0
        entry_price = 0.0

        if self.pm:
            has_position = self.pm.has_position()
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price

        # ---------------------------------------------------------
        # Logic
        # ---------------------------------------------------------

        # Volatility Check: ATR > Average ATR
        volatility_expanding = current['atr'] > current['atr_ma']

        # Trend Filter
        trend_up = current['close'] > current['sma_50']
        trend_down = current['close'] < current['sma_50']

        # ADX Filter (New Feature)
        trend_strong = current['adx'] > self.adx_threshold

        # Entry Logic
        if not has_position:
            # BUY: Breakout + Volatility + Trend + ADX + RSI
            if (current['close'] > current['bb_upper'] and
                volatility_expanding and
                trend_up and
                trend_strong and
                50 < current['rsi'] < 70):

                self.logger.info(f"BUY SIGNAL (V2): Price={current['close']}, ADX={current['adx']:.2f}")
                self.buy(self.quantity, current['close'])

            # SELL: Breakdown + Volatility + Trend + ADX + RSI
            elif (current['close'] < current['bb_lower'] and
                  volatility_expanding and
                  trend_down and
                  trend_strong and
                  30 < current['rsi'] < 50):

                self.logger.info(f"SELL SIGNAL (V2): Price={current['close']}, ADX={current['adx']:.2f}")
                self.sell(self.quantity, current['close'])

        # Exit Logic
        elif has_position:
            # Trailing Stop Logic (New Feature)
            # Trail SMA 20 (BB Mid)

            if pos_qty > 0: # Long
                stop_hit = current['close'] < current['sma_20'] # Trail SMA 20
                target_hit = current['close'] > (entry_price + (3.0 * current['atr']))

                if stop_hit or target_hit:
                    reason = "Trailing Stop (SMA 20)" if stop_hit else "Target"
                    self.logger.info(f"EXIT LONG ({reason}): Price={current['close']}")
                    self.sell(abs(pos_qty), current['close'])

            elif pos_qty < 0: # Short
                stop_hit = current['close'] > current['sma_20'] # Trail SMA 20
                target_hit = current['close'] < (entry_price - (3.0 * current['atr']))

                if stop_hit or target_hit:
                    reason = "Trailing Stop (SMA 20)" if stop_hit else "Target"
                    self.logger.info(f"EXIT SHORT ({reason}): Price={current['close']}")
                    self.buy(abs(pos_qty), current['close'])

    def generate_signal_internal(self, df):
        """Internal method for backtesting signal generation."""
        if df.empty:
            return "HOLD", 0.0, {}

        df = self.calculate_indicators(df)
        if len(df) < 50:
             return "HOLD", 0.0, {}

        current = df.iloc[-1]

        volatility_expanding = current['atr'] > current['atr_ma']
        trend_up = current['close'] > current['sma_50']
        trend_down = current['close'] < current['sma_50']
        trend_strong = current['adx'] > self.adx_threshold

        # Return details including ATR for dynamic sizing in backtester
        details = {
            "atr": current['atr'],
            "adx": current['adx'],
            "rsi": current['rsi']
        }

        if (current['close'] > current['bb_upper'] and
            volatility_expanding and
            trend_up and
            trend_strong and
            50 < current['rsi'] < 70):
            return "BUY", 1.0, details

        elif (current['close'] < current['bb_lower'] and
              volatility_expanding and
              trend_down and
              trend_strong and
              30 < current['rsi'] < 50):
            return "SELL", 1.0, details

        return "HOLD", 0.0, details

# Module-level wrapper for backtester
def generate_signal(df, client=None, symbol=None, params=None):
    # Instantiate strategy
    # passing client and symbol
    # params can be passed as kwargs
    kwargs = params or {}
    kwargs['symbol'] = symbol
    kwargs['client'] = client

    strat = MCXSmartStrategyV2(**kwargs)
    return strat.generate_signal_internal(df)

if __name__ == "__main__":
    MCXSmartStrategyV2.cli()
