#!/usr/bin/env python3
"""
NSE RSI MACD Strategy V2
Enhanced with ATR Trailing Stop.
Inherits from BaseStrategy.
"""
import os
import sys
import argparse
import logging
import pandas as pd
from datetime import datetime

# Add project root to path
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(current_dir)
    openalgo_root = os.path.dirname(strategies_dir)
    if strategies_dir not in sys.path:
        sys.path.insert(0, strategies_dir)
    if openalgo_root not in sys.path:
        sys.path.insert(0, openalgo_root)
except Exception:
    pass

try:
    from utils.base_strategy import BaseStrategy
    from utils.trading_utils import calculate_rsi, calculate_macd, calculate_atr
except ImportError:
    try:
        from strategies.utils.base_strategy import BaseStrategy
        from strategies.utils.trading_utils import calculate_rsi, calculate_macd, calculate_atr
    except ImportError:
        # Fallback
        sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
        from strategies.utils.base_strategy import BaseStrategy
        from strategies.utils.trading_utils import calculate_rsi, calculate_macd, calculate_atr

class NSERsiMacdStrategyV2(BaseStrategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.macd_fast = int(kwargs.get('macd_fast', 12))
        self.macd_slow = int(kwargs.get('macd_slow', 26))
        self.macd_signal = int(kwargs.get('macd_signal', 9))
        self.atr_period = int(kwargs.get('atr_period', 14))
        self.atr_multiplier = float(kwargs.get('atr_multiplier', 2.0))

        # State for Trailing Stop
        self.highest_high = 0.0
        self.lowest_low = float('inf')

    def cycle(self):
        # Determine exchange (NSE for stocks, NSE_INDEX for indices)
        exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

        # Fetch historical data
        df = self.fetch_history(days=5, symbol=self.symbol, exchange=exchange, interval=self.interval)

        if df.empty or len(df) < max(self.macd_slow, self.rsi_period, self.atr_period):
            self.logger.info("Waiting for sufficient data...")
            return

        # Calculate indicators
        rsi = self.calculate_rsi(df['close'], period=self.rsi_period)
        macd, signal_line, _ = self.calculate_macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
        atr = self.calculate_atr_series(df, period=self.atr_period)

        last = df.iloc[-1]
        prev = df.iloc[-2]
        current_price = last['close']
        current_rsi = rsi.iloc[-1]
        current_macd = macd.iloc[-1]
        current_signal = signal_line.iloc[-1]
        current_atr = atr.iloc[-1]

        self.logger.info(f"Price: {current_price}, RSI: {current_rsi:.2f}, MACD: {current_macd:.2f}, Signal: {current_signal:.2f}, ATR: {current_atr:.2f}")

        # Position management
        if self.pm and self.pm.has_position():
            pos_qty = self.pm.position

            # Update Trailing Stop State
            if pos_qty > 0:
                self.highest_high = max(self.highest_high, current_price)
                stop_loss = self.highest_high - (current_atr * self.atr_multiplier)

                # Exit Conditions
                bearish_crossover = (macd.iloc[-2] >= signal_line.iloc[-2]) and (current_macd < current_signal)
                stop_hit = current_price < stop_loss

                if stop_hit or bearish_crossover or current_rsi > 70:
                    reason = "Trailing Stop" if stop_hit else "MACD Cross" if bearish_crossover else "RSI Overbought"
                    self.logger.info(f"Exiting Long. Reason: {reason}. SL was {stop_loss:.2f}")
                    self.sell(abs(pos_qty), current_price)
                    # Reset state
                    self.highest_high = 0.0

            elif pos_qty < 0:
                self.lowest_low = min(self.lowest_low, current_price)
                stop_loss = self.lowest_low + (current_atr * self.atr_multiplier)

                bullish_crossover = (macd.iloc[-2] <= signal_line.iloc[-2]) and (current_macd > current_signal)
                stop_hit = current_price > stop_loss

                if stop_hit or bullish_crossover or current_rsi < 30:
                     reason = "Trailing Stop" if stop_hit else "MACD Cross" if bullish_crossover else "RSI Oversold"
                     self.logger.info(f"Exiting Short. Reason: {reason}. SL was {stop_loss:.2f}")
                     self.buy(abs(pos_qty), current_price)
                     self.lowest_low = float('inf')

        else:
            # Entry logic
            # Buy if MACD Crosses Above Signal AND RSI > 50
            bullish_crossover = (macd.iloc[-2] <= signal_line.iloc[-2]) and (current_macd > current_signal)

            if bullish_crossover and current_rsi > 50:
                qty = self.get_adaptive_quantity(current_price)
                self.logger.info(f"Entry signal detected (Bullish Trend). Buying {qty} at {current_price}")
                self.buy(qty, current_price)

                # Initialize Trailing Stop
                self.highest_high = current_price

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
        parser.add_argument('--macd_fast', type=int, default=12, help='MACD Fast Period')
        parser.add_argument('--macd_slow', type=int, default=26, help='MACD Slow Period')
        parser.add_argument('--macd_signal', type=int, default=9, help='MACD Signal Period')
        parser.add_argument('--atr_period', type=int, default=14, help='ATR Period')
        parser.add_argument('--atr_multiplier', type=float, default=2.0, help='ATR Multiplier for Stop')

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'rsi_period': 14,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'atr_period': 14,
        'atr_multiplier': 2.0
    }
    if params:
        strat_params.update(params)

    # Import locally to avoid top-level issues during test loading
    try:
        from strategies.utils.trading_utils import calculate_rsi, calculate_macd, calculate_atr
    except ImportError:
         try:
             from utils.trading_utils import calculate_rsi, calculate_macd, calculate_atr
         except ImportError:
             from openalgo.strategies.utils.trading_utils import calculate_rsi, calculate_macd, calculate_atr

    rsi = calculate_rsi(df['close'], period=strat_params['rsi_period'])
    macd, signal, _ = calculate_macd(df['close'], fast=strat_params['macd_fast'], slow=strat_params['macd_slow'], signal=strat_params['macd_signal'])

    bullish_crossover = (macd.shift(1) <= signal.shift(1)) & (macd > signal)
    bearish_crossover = (macd.shift(1) >= signal.shift(1)) & (macd < signal)

    last_idx = df.index[-1]

    if bullish_crossover.iloc[-1] and rsi.iloc[-1] > 50:
        return 'BUY', 1.0, {'reason': 'MACD Crossover + RSI'}

    if bearish_crossover.iloc[-1] or rsi.iloc[-1] > 70:
        return 'SELL', 1.0, {'reason': 'Exit'}

    return 'HOLD', 0.0, {}

if __name__ == "__main__":
    NSERsiMacdStrategyV2.cli()
