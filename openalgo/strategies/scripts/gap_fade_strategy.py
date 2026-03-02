#!/usr/bin/env python3
"""
Gap Fade Strategy
Fades opening gaps if a Reversal Candle confirms the direction.
Uses ADX trend filter (< 25) and RSI confirmation (> 60 / < 40) to filter out strong trend days.
"""
import logging
import pandas as pd

import strategy_preamble
from base_strategy import BaseStrategy
from trading_utils import calculate_adx, calculate_rsi

class GapFadeStrategy(BaseStrategy):
    params = {
        'symbol': 'NIFTY',
        'exchange': 'NSE_INDEX',
        'interval': '5m',
        'gap_threshold_pct': 0.3,
        'adx_threshold': 25,
        'rsi_overbought': 60,
        'rsi_oversold': 40
    }

    def setup(self):
        if self.symbol:
            self.name = f"GapFade_{self.symbol}"

    def generate_signal(self, df):
        if len(df) < 20:
            return 0, {}

        # Calculate indicators
        adx = calculate_adx(df)
        rsi = calculate_rsi(df['close'])

        # We need yesterday's close and today's open to determine gap
        current_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]

        current_adx = adx.iloc[-1] if not adx.empty else 0
        current_rsi = rsi.iloc[-1] if not rsi.empty else 50

        # Trend Filter: ADX < 25 (Choppy/Range-bound, good for fading)
        if current_adx >= self.adx_threshold:
            self.logger.debug(f"ADX ({current_adx:.2f}) >= {self.adx_threshold}, strong trend detected. No fade.")
            return 0, {}

        # Reversal Candle check (e.g. Close < Open for Gap Up)
        gap_up = current_candle['open'] > prev_candle['close'] * (1 + self.gap_threshold_pct/100)
        gap_down = current_candle['open'] < prev_candle['close'] * (1 - self.gap_threshold_pct/100)

        reversal_down = current_candle['close'] < current_candle['open']
        reversal_up = current_candle['close'] > current_candle['open']

        signal = 0
        if gap_up and reversal_down and current_rsi > self.rsi_overbought:
            signal = -1
        elif gap_down and reversal_up and current_rsi < self.rsi_oversold:
            signal = 1

        return signal, {
            'adx': current_adx,
            'rsi': current_rsi,
            'sl': current_candle['high'] if signal == -1 else current_candle['low'],
            'tp': current_candle['open'] - (current_candle['high'] - current_candle['low']) if signal == -1 else current_candle['open'] + (current_candle['high'] - current_candle['low'])
        }

    def cycle(self):
        # Fetch 2 days of 5-minute intraday data
        try:
            df = self.client.history(
                symbol=self.symbol,
                exchange=self.exchange,
                interval=self.interval,
                days=2
            )

            if df is None or df.empty:
                self.logger.warning(f"No data received for symbol {self.symbol}")
                return

            signal, data = self.generate_signal(df)

            if signal == 1:
                self.logger.info(f"Signal Buy {self.symbol} Price: {df['close'].iloc[-1]:.2f}")
                # Use execute_trade with computed SL and TP
                self.execute_trade(
                    symbol=self.symbol,
                    exchange=self.exchange,
                    action="BUY",
                    quantity=self.quantity,
                    stop_loss=data['sl'],
                    take_profit=data['tp']
                )
            elif signal == -1:
                self.logger.info(f"Signal Sell {self.symbol} Price: {df['close'].iloc[-1]:.2f}")
                self.execute_trade(
                    symbol=self.symbol,
                    exchange=self.exchange,
                    action="SELL",
                    quantity=self.quantity,
                    stop_loss=data['sl'],
                    take_profit=data['tp']
                )

        except Exception as e:
            self.logger.error(f"Error in cycle: {e}")

if __name__ == "__main__":
    strategy = GapFadeStrategy()
    strategy.run()
