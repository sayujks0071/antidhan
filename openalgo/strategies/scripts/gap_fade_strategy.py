#!/usr/bin/env python3
import pandas as pd
from strategy_preamble import BaseStrategy

class GapFadeStrategy(BaseStrategy):
    def setup(self):
        self.name = "GapFadeStrategy"
        self.interval = '5m'
        self.exchange = 'NSE'

        self.adx_period = getattr(self, "adx_period", 14)
        self.rsi_period = getattr(self, "rsi_period", 14)

    def cycle(self):
        df = self.fetch_and_prepare_data(days=2, min_rows=20)
        if df is None or len(df) < 2:
            return

        last = df.iloc[-1]
        prev = df.iloc[-2]

        adx = self.calculate_adx(df, period=self.adx_period)
        rsi = self.calculate_rsi(df['close'], period=self.rsi_period)

        # Gap Up
        if last['open'] > prev['high'] and adx < 25 and rsi > 60:
            if last['close'] < last['open']:  # Reversal Candle
                self.logger.info("Gap Up Fade condition met.")
                self.execute_trade('SHORT', 1, last['close'])

        # Gap Down
        elif last['open'] < prev['low'] and adx < 25 and rsi < 40:
            if last['close'] > last['open']:  # Reversal Candle
                self.logger.info("Gap Down Fade condition met.")
                self.execute_trade('LONG', 1, last['close'])

    def get_signal(self, df):
        if df.empty or len(df) < 2: return 'HOLD', {}, {}

        last = df.iloc[-1]
        prev = df.iloc[-2]

        adx = self.calculate_adx(df, period=self.adx_period)
        rsi = self.calculate_rsi(df['close'], period=self.rsi_period)

        details = {'close': last['close'], 'adx': adx, 'rsi': rsi}

        if last['open'] > prev['high'] and adx < 25 and rsi > 60:
            if last['close'] < last['open']:
                return 'SELL', 1.0, details
        elif last['open'] < prev['low'] and adx < 25 and rsi < 40:
            if last['close'] > last['open']:
                return 'BUY', 1.0, details

        return 'HOLD', 0.0, details

generate_signal = GapFadeStrategy.backtest_signal

if __name__ == "__main__":
    GapFadeStrategy.cli()
