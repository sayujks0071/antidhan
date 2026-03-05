#!/usr/bin/env python3
"""
MCX Crude Oil Trend Strategy
MCX Commodity trading strategy with EMA, RSI, and ATR analysis
Refactored to inherit from BaseStrategy (DRY).
"""
import os
import sys
import logging
import argparse
import pandas as pd
from datetime import datetime

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

class MCXCrudeOilTrendStrategy(BaseStrategy):
    def setup(self):
        # Default Parameters if not provided
        self.period_rsi = int(getattr(self, "period_rsi", 14))
        self.period_atr = int(getattr(self, "period_atr", 14))
        self.period_ema = int(getattr(self, "period_ema", 20))

        # Multi-factor filters
        self.seasonality_score = int(getattr(self, "seasonality_score", 50))
        self.usd_inr_volatility = float(getattr(self, "usd_inr_volatility", 0.0))

    def calculate_indicators(self, df):
        """Calculate technical indicators using BaseStrategy helpers."""
        df['rsi'] = self.calculate_rsi(df['close'], period=self.period_rsi)
        df['atr'] = self.calculate_atr_series(df, period=self.period_atr)
        df['ema_fast'] = self.calculate_ema(df['close'], period=self.period_ema)
        return df

    def cycle(self):
        """Main execution logic for live trading."""
        # Fetch Data (15m default based on original script)
        df = self.fetch_history(days=5, interval="15m")
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

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        base_qty = self.quantity
        if self.pm:
            # Use Adaptive Sizing
            try:
                base_qty = self.get_adaptive_quantity(current['close'], risk_pct=1.0)
            except Exception:
                base_qty = self.quantity

        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size.")
            base_qty = max(1, int(base_qty * 0.7))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic
        # Buy: Close > EMA AND RSI > 50
        buy_signal = (current["close"] > current["ema_fast"]) and (current["rsi"] > 50)
        # Sell: Close < EMA AND RSI < 50
        sell_signal = (current["close"] < current["ema_fast"]) and (current["rsi"] < 50)

        if not has_position:
            if buy_signal:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.buy(base_qty, current['close'])
            elif sell_signal:
                self.logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.sell(base_qty, current['close'])

        # Exit Logic
        elif has_position:
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
                self.logger.info(f"EXIT: {reason}")
                action = "SELL" if pos_qty > 0 else "BUY"
                self.execute_trade(action, abs(pos_qty), current['close'])

    def generate_signal_internal(self, df):
        """Internal method for backtesting signal generation."""
        if df.empty:
            return "HOLD", 0.0, {}

        df = self.calculate_indicators(df)
        if len(df) < 50:
             return "HOLD", 0.0, {}

        current = df.iloc[-1]

        buy_signal = (current["close"] > current["ema_fast"]) and (current["rsi"] > 50)
        sell_signal = (current["close"] < current["ema_fast"]) and (current["rsi"] < 50)

        details = {
            "rsi": current['rsi'],
            "ema": current['ema_fast'],
            "atr": current['atr']
        }

        if buy_signal:
            return "BUY", 1.0, details
        elif sell_signal:
            return "SELL", 1.0, details

        return "HOLD", 0.0, details

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--period_ema", type=int, default=20, help="EMA Period")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %")

# Module-level wrapper for backtester
def generate_signal(df, client=None, symbol=None, params=None):
    kwargs = params or {}
    kwargs['symbol'] = symbol
    kwargs['client'] = client

    strat = MCXCrudeOilTrendStrategy(**kwargs)
    return strat.generate_signal_internal(df)

if __name__ == "__main__":
    MCXCrudeOilTrendStrategy.cli()
