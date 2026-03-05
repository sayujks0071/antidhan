#!/usr/bin/env python3
"""
Gap Fade Strategy
Fades opening gaps if a Reversal Candle confirms the direction.
Includes ADX trend filter to avoid strong momentum markets ('Gap and Go') and RSI confirmation.
"""
import logging
import pandas as pd
from datetime import datetime, time

# Import using strategy_preamble
from strategy_preamble import BaseStrategy

class GapFadeStrategy(BaseStrategy):
    def setup(self):
        if self.symbol:
            self.name = f"GapFade_{self.symbol}"

        self.stop_loss_pct = getattr(self, "stop_loss_pct", 1.0)
        self.target_pct = getattr(self, "target_pct", 2.0)
        self.gap_threshold_pct = getattr(self, "gap_threshold_pct", 0.5)
        self.adx_period = getattr(self, "adx_period", 14)
        self.rsi_period = getattr(self, "rsi_period", 14)

        # State
        self.traded_today = False
        self.current_day = None

    def cycle(self):
        """
        Main Strategy Logic Execution Cycle
        """
        now_date = datetime.now().date()
        if self.current_day != now_date:
            self.current_day = now_date
            self.traded_today = False

        if self.traded_today or (self.pm and self.pm.has_position()):
            # Only manage existing position
            self.manage_position()
            return

        # Fetch 2 days of 5-minute intraday data
        df = self.fetch_and_prepare_data(days=2, interval='5m')
        if df is None or len(df) < 20:
            return

        # Calculate indicators
        df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
        adx = self.calculate_adx(df, period=self.adx_period)

        # Ensure we have at least one full candle today
        today_data = df[df.index.date == now_date]
        if today_data.empty:
            return

        first_candle = today_data.iloc[0]
        last_candle = today_data.iloc[-1]

        # Get previous day's close
        prev_day_data = df[df.index.date < now_date]
        if prev_day_data.empty:
            return
        prev_close = prev_day_data.iloc[-1]['close']

        # Gap calculation
        gap_pct = ((first_candle['open'] - prev_close) / prev_close) * 100

        # ADX trend filter (< 25) to filter out strong trend days
        if adx >= 25:
            self.logger.info(f"ADX too high ({adx:.2f} >= 25). Skipping trade as it might be a Gap and Go.")
            return

        # Reversal Candle confirmation (e.g. Close < Open for Gap Up)
        if gap_pct > self.gap_threshold_pct:
            # Gap Up: Expecting reversal, look for Close < Open and RSI < 40 or similar logic.
            # Actually for a fade we want overbought RSI. Wait, if it gaps up we fade it (short).
            # The prompt says: "RSI confirmation (> 60 / < 40)". So Gap Up -> Fade -> Short -> RSI > 60.
            if last_candle['close'] < last_candle['open'] and df['rsi'].iloc[-1] > 60:
                self.logger.info(f"Gap Up Fade Entry Signal: Gap={gap_pct:.2f}%, Reversal Candle=True, RSI={df['rsi'].iloc[-1]:.2f}, ADX={adx:.2f}")

                # SL/TP based on the first candle's High/Low
                sl_price = first_candle['high']
                entry_price = last_candle['close']

                if sl_price <= entry_price:
                    sl_price = entry_price * (1 + (self.stop_loss_pct / 100))

                risk = sl_price - entry_price
                tp_price = entry_price - (risk * (self.target_pct / self.stop_loss_pct))

                qty = self.get_adaptive_quantity(entry_price, risk_pct=1.0, capital=500000)
                if qty < 1: qty = 1

                self.execute_trade('SELL', qty, entry_price)
                self.sl_price = sl_price
                self.tp_price = tp_price
                self.direction = -1
                self.quantity = qty
                self.traded_today = True

        elif gap_pct < -self.gap_threshold_pct:
            # Gap Down: Expecting reversal, look for Close > Open and RSI < 40.
            if last_candle['close'] > last_candle['open'] and df['rsi'].iloc[-1] < 40:
                self.logger.info(f"Gap Down Fade Entry Signal: Gap={gap_pct:.2f}%, Reversal Candle=True, RSI={df['rsi'].iloc[-1]:.2f}, ADX={adx:.2f}")

                # SL/TP based on the first candle's High/Low
                sl_price = first_candle['low']
                entry_price = last_candle['close']

                if sl_price >= entry_price:
                    sl_price = entry_price * (1 - (self.stop_loss_pct / 100))

                risk = entry_price - sl_price
                tp_price = entry_price + (risk * (self.target_pct / self.stop_loss_pct))

                qty = self.get_adaptive_quantity(entry_price, risk_pct=1.0, capital=500000)
                if qty < 1: qty = 1

                self.execute_trade('BUY', qty, entry_price)
                self.sl_price = sl_price
                self.tp_price = tp_price
                self.direction = 1
                self.quantity = qty
                self.traded_today = True

    def manage_position(self):
        # Fetch data to check SL/TP
        if not hasattr(self, 'direction'):
            return

        df = self.fetch_and_prepare_data(days=1, interval='5m')
        if df is None or df.empty:
            return

        last_price = df.iloc[-1]['close']

        if self.direction == 1: # LONG
            if last_price <= self.sl_price:
                self.logger.info(f"SL Hit at {last_price:.2f}")
                self.execute_trade('SELL', self.quantity, last_price)
                self.direction = 0
            elif last_price >= self.tp_price:
                self.logger.info(f"TP Hit at {last_price:.2f}")
                self.execute_trade('SELL', self.quantity, last_price)
                self.direction = 0
        elif self.direction == -1: # SHORT
            if last_price >= self.sl_price:
                self.logger.info(f"SL Hit at {last_price:.2f}")
                self.execute_trade('BUY', self.quantity, last_price)
                self.direction = 0
            elif last_price <= self.tp_price:
                self.logger.info(f"TP Hit at {last_price:.2f}")
                self.execute_trade('BUY', self.quantity, last_price)
                self.direction = 0

    def get_signal(self, df):
        """
        Generate signal for backtesting
        """
        if df.empty or len(df) < 20: return 'HOLD', {}, {}

        df = df.sort_index()
        df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
        adx = self.calculate_adx(df, period=self.adx_period)

        last = df.iloc[-1]

        details = {
            'close': last['close'],
            'adx': adx,
            'rsi': df['rsi'].iloc[-1] if not pd.isna(df['rsi'].iloc[-1]) else 50
        }

        return 'HOLD', 0.0, details

# Module level wrapper for backtesting
generate_signal = GapFadeStrategy.get_signal

if __name__ == "__main__":
    GapFadeStrategy.cli()
