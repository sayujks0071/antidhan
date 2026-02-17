#!/usr/bin/env python3
"""
NSE RSI MACD Strategy with ADX Filter
Strategy for NSE Equities using RSI and MACD for Trend Following.
Entry: Buy when MACD Line crosses above Signal Line AND RSI > 50 AND ADX > 25.
Exit: Sell when MACD Line crosses below Signal Line OR RSI > 70.
"""
import os
import sys
import logging
import pandas as pd

# Add repo root to path to allow imports (if running as script)
try:
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol
except ImportError:
    # Try setting path to find utils
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol

class NSERsiMacdStrategy(BaseStrategy):
    def setup(self):
        """Initialize strategy parameters"""
        if self.symbol:
            self.name = f"NSE_RSI_MACD_{self.symbol}"

        # Strategy Parameters
        self.rsi_period = int(getattr(self, 'rsi_period', 14))
        self.macd_fast = int(getattr(self, 'macd_fast', 12))
        self.macd_slow = int(getattr(self, 'macd_slow', 26))
        self.macd_signal = int(getattr(self, 'macd_signal', 9))
        self.adx_period = int(getattr(self, 'adx_period', 14))
        self.adx_threshold = int(getattr(self, 'adx_threshold', 25))

    def cycle(self):
        """
        Main Strategy Logic Execution Cycle
        """
        # Determine exchange
        exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

        # Fetch historical data (enough for indicators)
        df = self.fetch_history(days=5, exchange=exchange)
        if df.empty or len(df) < max(self.macd_slow, self.rsi_period, self.adx_period) + 5:
            self.logger.warning(f"Insufficient data for {self.symbol}: {len(df)} rows.")
            return

        # Calculate Indicators
        try:
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            macd, signal_line, _ = self.calculate_macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
            df['macd'] = macd
            df['signal'] = signal_line
            df['adx'] = self.calculate_adx_series(df, period=self.adx_period)
        except Exception as e:
            self.logger.error(f"Indicator calculation failed: {e}")
            return

        last = df.iloc[-1]
        prev = df.iloc[-2]

        current_price = last['close']
        current_rsi = last['rsi']
        current_macd = last['macd']
        current_signal = last['signal']
        current_adx = last['adx']

        self.logger.info(f"Price: {current_price:.2f}, RSI: {current_rsi:.2f}, MACD: {current_macd:.2f}, Signal: {current_signal:.2f}, ADX: {current_adx:.2f}")

        # Position Management
        if self.pm and self.pm.has_position():
            # Exit Logic: Sell if MACD Crosses Below Signal OR RSI > 70
            bearish_crossover = (prev['macd'] >= prev['signal']) and (last['macd'] < last['signal'])

            if bearish_crossover or current_rsi > 70:
                reason = "MACD Cross Under" if bearish_crossover else "RSI Overbought"
                self.logger.info(f"Exiting position. Reason: {reason}")
                # Use absolute position size for closing
                current_pos = abs(self.pm.position) if hasattr(self.pm, 'position') else self.quantity
                self.execute_trade('SELL', current_pos, current_price)
        else:
            # Entry Logic: Buy if MACD Crosses Above Signal AND RSI > 50 AND ADX > 25
            bullish_crossover = (prev['macd'] <= prev['signal']) and (last['macd'] > last['signal'])

            if bullish_crossover and current_rsi > 50 and current_adx > self.adx_threshold:
                qty = self.quantity
                # Adaptive Sizing
                try:
                    adaptive_qty = self.get_adaptive_quantity(current_price)
                    qty = max(1, adaptive_qty)
                except:
                    pass

                self.logger.info(f"Entry signal detected (Bullish Trend + Strong ADX). Buying {qty} at {current_price}")
                self.execute_trade('BUY', qty, current_price)

    def get_signal(self, df):
        """
        Generate signal for backtesting
        """
        if df.empty or len(df) < max(self.macd_slow, self.rsi_period, self.adx_period) + 5:
            return 'HOLD', 0.0, {}

        # Calculate Indicators
        try:
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            macd, signal_line, _ = self.calculate_macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
            df['macd'] = macd
            df['signal'] = signal_line
            df['adx'] = self.calculate_adx_series(df, period=self.adx_period)
        except:
             return 'HOLD', 0.0, {}

        last = df.iloc[-1]
        prev = df.iloc[-2]

        bullish_crossover = (prev['macd'] <= prev['signal']) and (last['macd'] > last['signal'])
        bearish_crossover = (prev['macd'] >= prev['signal']) and (last['macd'] < last['signal'])

        details = {
            'close': last['close'],
            'rsi': last['rsi'],
            'macd': last['macd'],
            'adx': last['adx']
        }

        if bullish_crossover and last['rsi'] > 50 and last['adx'] > self.adx_threshold:
            return 'BUY', 1.0, details

        if bearish_crossover or last['rsi'] > 70:
            return 'SELL', 1.0, details

        return 'HOLD', 0.0, details

if __name__ == "__main__":
    NSERsiMacdStrategy.cli()
