#!/usr/bin/env python3
"""
NSE RSI MACD Strategy with ADX Filter
Strategy for NSE Equities using RSI and MACD for Trend Following.
Entry: Buy when MACD Line crosses above Signal Line AND RSI > 50 AND ADX > 25.
Exit: Sell when MACD Line crosses below Signal Line OR RSI > 70.
Inherits from BaseStrategy for code reduction.
"""
import strategy_preamble
from base_strategy import BaseStrategy

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

        # Declarative Indicators Configuration for BaseStrategy automation
        self.indicators = {
            'rsi': self.rsi_period,
            'macd': (self.macd_fast, self.macd_slow, self.macd_signal),
            'adx': self.adx_period
        }

    def generate_signal(self, df):
        """
        Generate signal using pre-calculated indicators.
        Returns: ('BUY'/'SELL'/'EXIT'/'HOLD', quantity [optional], details [optional])
        """
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
                self.logger.info(f"Signal: EXIT. Reason: {reason}")
                return "EXIT"
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

                self.logger.info(f"Signal: BUY. Buying {qty} at {current_price}")
                return "BUY", qty

        return "HOLD"

    def get_signal(self, df):
        """
        Backtesting signal generation (Optional, can rely on generate_signal if compatible)
        But keeping for legacy compatibility if needed.
        """
        # Actually BaseStrategy can use generate_signal for backtesting too if we standardized the output.
        # But get_signal returns (signal, confidence, details).
        # Let's adapt generate_signal result here.
        res = self.generate_signal(df)
        if res == "EXIT": return "SELL", 1.0, {}
        if isinstance(res, tuple) and res[0] == "BUY": return "BUY", 1.0, {}
        return "HOLD", 0.0, {}

if __name__ == "__main__":
    NSERsiMacdStrategy.cli()
