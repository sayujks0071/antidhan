#!/usr/bin/env python3
"""
MCX Silver Momentum Strategy
MCX Commodity trading strategy with RSI, ATR, and SMA analysis.
Refactored to inherit from BaseStrategy (DRY).
"""
import os
import sys
import argparse
import pandas as pd
import numpy as np

# Use strategy_preamble for standardized imports
from strategy_preamble import BaseStrategy

class MCXSilverMomentumStrategy(BaseStrategy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.period_rsi = kwargs.get("period_rsi", 14)
        self.period_atr = kwargs.get("period_atr", 14)
        self.seasonality_score = kwargs.get("seasonality_score", 50)
        self.usd_inr_volatility = kwargs.get("usd_inr_volatility", 0.0)

    @classmethod
    def add_arguments(cls, parser):
        """Add custom arguments for this strategy."""
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

    def calculate_indicators(self, df):
        """Calculate technical indicators."""
        # RSI
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)

        # ATR
        df["atr"] = self.calculate_atr_series(df, period=self.period_atr)

        # SMA 50
        df["sma_50"] = self.calculate_sma(df["close"], period=50)

        return df

    def cycle(self):
        """Main execution logic."""
        # Fetch Data (15m default based on original script)
        df = self.fetch_history(days=10, interval="15m")
        if df.empty or len(df) < 50:
            self.logger.warning("Insufficient data.")
            return

        df = self.calculate_indicators(df)
        self.check_signals(df)

    def check_signals(self, df):
        """Check entry and exit conditions."""
        current = df.iloc[-1]

        has_position = False
        pos_qty = 0
        entry_price = 0.0

        if self.pm:
            has_position = self.pm.has_position()
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 0.8

        base_qty = self.quantity # Use configured quantity

        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Trading effectively halted or reduced.")
            if self.usd_inr_volatility > 1.5:
                self.logger.warning("Volatility too high, skipping trade.")
                return

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        close = current['close']
        sma_50 = current['sma_50']
        rsi = current['rsi']
        atr = current['atr']

        # Entry Logic
        if not has_position:
            # BUY
            if close > sma_50 and rsi > 55:
                self.logger.info(f"BUY SIGNAL: Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                self.buy(base_qty, close)
            # SELL (Short)
            elif close < sma_50 and rsi < 45:
                self.logger.info(f"SELL SIGNAL: Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                self.sell(base_qty, close)

        # Exit Logic
        elif has_position:
            is_long = pos_qty > 0

            stop_loss_dist = 2 * atr
            take_profit_dist = 4 * atr

            exit_signal = False
            exit_reason = ""

            if is_long:
                if close < (entry_price - stop_loss_dist):
                    exit_signal = True
                    exit_reason = "Stop Loss"
                elif close > (entry_price + take_profit_dist):
                    exit_signal = True
                    exit_reason = "Take Profit"
                elif close < sma_50 or rsi < 40:
                     exit_signal = True
                     exit_reason = "Trend Reversal"
            else: # Short
                if close > (entry_price + stop_loss_dist):
                    exit_signal = True
                    exit_reason = "Stop Loss"
                elif close < (entry_price - take_profit_dist):
                    exit_signal = True
                    exit_reason = "Take Profit"
                elif close > sma_50 or rsi > 60:
                    exit_signal = True
                    exit_reason = "Trend Reversal"

            if exit_signal:
                self.logger.info(f"EXIT ({exit_reason}): Price={close}")
                self.sell(abs(pos_qty), close) if is_long else self.buy(abs(pos_qty), close)

    def generate_signal_internal(self, df):
        """Internal signal generation for backtester."""
        if df.empty:
            return "HOLD", 0.0, {}

        df = self.calculate_indicators(df)
        current = df.iloc[-1]

        # Check if 'sma_50' exists
        if 'sma_50' not in current or pd.isna(current['sma_50']):
             return "HOLD", 0.0, {}

        close = current['close']
        sma_50 = current['sma_50']
        rsi = current['rsi']

        # BUY
        if close > sma_50 and rsi > 55:
            return "BUY", 1.0, {"reason": f"Price > SMA50 & RSI({rsi:.1f}) > 55"}

        # SELL (Short)
        if close < sma_50 and rsi < 45:
             return "SELL", 1.0, {"reason": f"Price < SMA50 & RSI({rsi:.1f}) < 45"}

        return "HOLD", 0.0, {}

# Module-level wrapper for backtester
def generate_signal(df, client=None, symbol=None, params=None):
    kwargs = params or {}
    kwargs['symbol'] = symbol
    kwargs['client'] = client

    # Defaults
    if 'period_rsi' not in kwargs: kwargs['period_rsi'] = 14
    if 'period_atr' not in kwargs: kwargs['period_atr'] = 14

    strat = MCXSilverMomentumStrategy(**kwargs)
    return strat.generate_signal_internal(df)

if __name__ == "__main__":
    MCXSilverMomentumStrategy.cli()
