#!/usr/bin/env python3
"""
NSE RSI MACD Strategy V3 with Multi-Timeframe Confirmation
Strategy for NSE Equities using RSI and MACD for Trend Following.
Entry: Buy when MACD Line crosses above Signal Line AND RSI > 50 AND ADX > 25 AND Close > SMA 200.
Exit: Sell when MACD Line crosses below Signal Line OR RSI > 70.
Inherits from BaseStrategy for code reduction.
"""
import os
import sys

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

class NSERsiMacdStrategyV3(BaseStrategy):
    def setup(self):
        """Initialize strategy parameters"""
        if self.symbol:
            self.name = f"NSE_RSI_MACD_V3_{self.symbol}"

        # Strategy Parameters
        self.rsi_period = int(getattr(self, 'rsi_period', 14))
        self.macd_fast = int(getattr(self, 'macd_fast', 12))
        self.macd_slow = int(getattr(self, 'macd_slow', 26))
        self.macd_signal = int(getattr(self, 'macd_signal', 9))
        self.adx_period = int(getattr(self, 'adx_period', 14))
        self.adx_threshold = int(getattr(self, 'adx_threshold', 25))
        self.sma_period = int(getattr(self, 'sma_period', 200)) # Multi-Timeframe Confirmation

        # Declarative Indicators Configuration for BaseStrategy automation
        self.indicators = {
            'rsi': self.rsi_period,
            'macd': (self.macd_fast, self.macd_slow, self.macd_signal),
            'adx': self.adx_period,
            'sma_long': self.sma_period
        }

    def generate_signal(self, df):
        """
        Generate signal using pre-calculated indicators.
        Returns: ('BUY'/'SELL'/'EXIT'/'HOLD', quantity [optional], details [optional])
        """
        # Determine exchange
        exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

        # VIX Filter (Equity Curve Protection)
        vix = self.get_vix()
        size_multiplier, _ = self.calculate_vix_volatility_multiplier(vix)

        if vix > 35:
            self.logger.warning(f"Extreme VIX ({vix:.2f}) detected! Skipping entry.")
            return

        # Fetch historical data (enough for indicators)
        df = self.fetch_history(days=10, exchange=exchange)
        if df.empty or len(df) < max(self.macd_slow, self.rsi_period, self.adx_period, self.sma_period) + 5:
            self.logger.warning(f"Insufficient data for {self.symbol}: {len(df)} rows.")
            return

        # Calculate Indicators
        try:
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            macd, signal_line, _ = self.calculate_macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
            df['macd'] = macd
            df['signal'] = signal_line
            df['adx'] = self.calculate_adx_series(df, period=self.adx_period)
            df['sma_long'] = self.calculate_sma(df['close'], period=self.sma_period)
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
        current_sma_long = last['sma_long']

        self.logger.info(f"Price: {current_price:.2f}, RSI: {current_rsi:.2f}, MACD: {current_macd:.2f}, Signal: {current_signal:.2f}, ADX: {current_adx:.2f}, SMA({self.sma_period}): {current_sma_long:.2f}")

        # Position Management
        if self.pm and self.pm.has_position():
            # Exit Logic: Sell if MACD Crosses Below Signal OR RSI > 70
            bearish_crossover = (prev['macd'] >= prev['signal']) and (last['macd'] < last['signal'])

            if bearish_crossover or current_rsi > 70:
                reason = "MACD Cross Under" if bearish_crossover else "RSI Overbought"
                self.logger.info(f"Signal: EXIT. Reason: {reason}")
                return "EXIT"
        else:
            # Entry Logic: Buy if MACD Crosses Above Signal AND RSI > 50 AND ADX > 25 AND Price > SMA 200
            bullish_crossover = (prev['macd'] <= prev['signal']) and (last['macd'] > last['signal'])
            uptrend_confirmed = current_price > current_sma_long

            if bullish_crossover and current_rsi > 50 and current_adx > self.adx_threshold and uptrend_confirmed:
                qty = self.quantity
                # Adaptive Sizing with VIX Multiplier
                try:
                    adaptive_qty = self.get_adaptive_quantity(current_price)
                    qty = max(1, int(adaptive_qty * size_multiplier))
                except:
                    pass

                self.logger.info(f"Entry signal detected (Bullish Trend + Strong ADX + SMA Confirmed). Buying {qty} (VIX Mult: {size_multiplier}) at {current_price}")
                self.execute_trade('BUY', qty, current_price)

    def get_signal(self, df):
        """
        Backtesting signal generation (Optional, can rely on generate_signal if compatible)
        But keeping for legacy compatibility if needed.
        """
        if df.empty or len(df) < max(self.macd_slow, self.rsi_period, self.adx_period, self.sma_period) + 5:
            return 'HOLD', 0.0, {}

        # Calculate Indicators
        try:
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            macd, signal_line, _ = self.calculate_macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
            df['macd'] = macd
            df['signal'] = signal_line
            df['adx'] = self.calculate_adx_series(df, period=self.adx_period)
            df['sma_long'] = self.calculate_sma(df['close'], period=self.sma_period)

            last = df.iloc[-1]
            prev = df.iloc[-2]

            bullish_crossover = (prev['macd'] <= prev['signal']) and (last['macd'] > last['signal'])
            bearish_crossover = (prev['macd'] >= prev['signal']) and (last['macd'] < last['signal'])
            uptrend_confirmed = last['close'] > last['sma_long']

            details = {
                'close': last['close'],
                'rsi': last['rsi'],
                'macd': last['macd'],
                'adx': last['adx'],
                'sma_long': last['sma_long']
            }

            if bullish_crossover and last['rsi'] > 50 and last['adx'] > self.adx_threshold and uptrend_confirmed:
                return 'BUY', 1.0, details

            if bearish_crossover or last['rsi'] > 70:
                return 'SELL', 1.0, details

            return 'HOLD', 0.0, details

        except:
             return 'HOLD', 0.0, {}

if __name__ == "__main__":
    NSERsiMacdStrategyV3.cli()
