#!/usr/bin/env python3
"""
NSE Bollinger Bands + RSI Strategy
Entry: Close < Lower Band AND RSI < 30
Exit: Close > Upper Band OR RSI > 70
"""
import logging
import pandas as pd
from datetime import datetime, timedelta

from strategy_preamble import BaseStrategy

class NSEBollingerRSIStrategy(BaseStrategy):
    params = {
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0,
        'risk_pct': 2.0
    }

    def __init__(self, symbol, **kwargs):
        super().__init__(
            name=f"NSE_Bollinger_{symbol}",
            symbol=symbol,
            exchange="NSE",
            interval="5m",
            **kwargs
        )

    def get_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.rsi_period, self.bb_period):
            return 'HOLD', 0.0, {}

        # Calculate indicators
        try:
            df = df.copy()
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            df['sma'], df['upper'], df['lower'] = self.calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
        except Exception as e:
            self.logger.error(f"Indicator calculation error: {e}")
            return 'HOLD', 0.0, {}

        last = df.iloc[-1]
        close = last['close']
        rsi = last['rsi']
        lower = last['lower']
        upper = last['upper']

        # Entry logic: Close < Lower Band AND RSI < 30 (Oversold)
        if close < lower and rsi < 30:
            return 'BUY', 1.0, {
                'reason': 'Oversold (RSI < 30) & Below Lower Band',
                'price': close,
                'rsi': rsi,
                'lower_band': lower
            }

        # Exit logic: Close > Upper Band OR RSI > 70 (Overbought)
        if close > upper or rsi > 70:
             return 'SELL', 1.0, {
                'reason': 'Overbought (RSI > 70) or Above Upper Band',
                'price': close,
                'rsi': rsi,
                'upper_band': upper
            }

        return 'HOLD', 0.0, {}

# Backtesting support
generate_signal = NSEBollingerRSIStrategy.backtest_signal

if __name__ == "__main__":
    NSEBollingerRSIStrategy.cli()
