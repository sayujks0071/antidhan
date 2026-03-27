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
            'adx': self.adx_period,
            'atr': 14
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

        if df.empty or len(df) < max(self.macd_slow, self.rsi_period, self.adx_period) + 5:
            self.logger.warning(f"Insufficient data for {self.symbol}: {len(df)} rows.")
            return

        # Data Validation (ensure indicators exist)
        required_cols = ['rsi', 'macd', 'signal', 'adx', 'atr']
        for col in required_cols:
            if col not in df.columns:
                self.logger.error(f"Missing indicator column: {col}")
                return

        last = df.iloc[-1]
        prev = df.iloc[-2]

        current_price = last['close']
        current_rsi = last['rsi']
        current_macd = last['macd']
        current_signal = last['signal']
        current_adx = last['adx']
        current_atr = last['atr']

        self.logger.info(f"Price: {current_price:.2f}, RSI: {current_rsi:.2f}, MACD: {current_macd:.2f}, Signal: {current_signal:.2f}, ADX: {current_adx:.2f}, ATR: {current_atr:.2f}")

        # Position Management
        if self.pm and self.pm.has_position():
            # Exit Logic: Sell if MACD Crosses Below Signal OR RSI > 80 (Overbought Extreme)
            # Added ATR Trailing Stop
            entry_price = self.pm.entry_price
            stop_loss_price = entry_price - (2.0 * current_atr)

            bearish_crossover = (prev['macd'] >= prev['signal']) and (last['macd'] < last['signal'])

            # Stricter Exit: RSI > 80 or RSI > 70 AND Bearish Crossover
            rsi_exit = current_rsi > 80 or (current_rsi > 70 and bearish_crossover)
            stop_loss_hit = current_price < stop_loss_price

            if stop_loss_hit:
                self.logger.info(f"Signal: EXIT. Reason: Stop Loss Hit ({current_price:.2f} < {stop_loss_price:.2f})")
                return "EXIT"

            if bearish_crossover or rsi_exit:
                reason = "MACD Cross Under" if bearish_crossover else "RSI Overbought (Extreme)"
                self.logger.info(f"Signal: EXIT. Reason: {reason}")
                return "EXIT"
        else:
            # Entry Logic: Buy if MACD Crosses Above Signal AND RSI > 50 AND ADX > 25
            bullish_crossover = (prev['macd'] <= prev['signal']) and (last['macd'] > last['signal'])

            if bullish_crossover and current_rsi > 50 and current_adx > self.adx_threshold:
                qty = self.quantity
                # Adaptive Sizing with VIX Multiplier
                try:
                    adaptive_qty = self.get_adaptive_quantity(current_price)
                    qty = max(1, int(adaptive_qty * size_multiplier))
                except:
                    pass

                self.logger.info(f"Entry signal detected (Bullish Trend + Strong ADX). Buying {qty} (VIX Mult: {size_multiplier}) at {current_price}")
                self.execute_trade('BUY', qty, current_price)

    def get_signal(self, df):
        """
        Backtesting signal generation.
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
            df['atr'] = self.calculate_atr_series(df, period=14)

            last = df.iloc[-1]
            prev = df.iloc[-2]

            bullish_crossover = (prev['macd'] <= prev['signal']) and (last['macd'] > last['signal'])
            bearish_crossover = (prev['macd'] >= prev['signal']) and (last['macd'] < last['signal'])

            details = {
                'close': last['close'],
                'rsi': last['rsi'],
                'macd': last['macd'],
                'adx': last['adx'],
                'atr': last['atr']
            }

            # Note: Backtesting usually assumes no prior position state unless passed explicitly.
            # So Stop Loss logic is hard to implement here without position context.
            # We stick to Entry/Exit signals.

            if bullish_crossover and last['rsi'] > 50 and last['adx'] > self.adx_threshold:
                return 'BUY', 1.0, details

            # Stricter Exit
            rsi_exit = last['rsi'] > 80 or (last['rsi'] > 70 and bearish_crossover)

            if bearish_crossover or rsi_exit:
                return 'SELL', 1.0, details

            return 'HOLD', 0.0, details

        except Exception as e:
             self.logger.error(f"Backtest Signal Error: {e}")
             return 'HOLD', 0.0, {}


if __name__ == "__main__":
    NSERsiMacdStrategy.cli()
