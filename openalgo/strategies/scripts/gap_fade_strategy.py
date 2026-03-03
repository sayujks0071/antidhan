"""
Gap Fade Strategy
This strategy fades opening gaps if a Reversal Candle confirms the direction.
"""

from strategy_preamble import BaseStrategy
from strategies.utils.trading_utils import APIClient, PositionManager

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class GapFadeStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.params = {
            'symbol': 'NIFTY',
            'exchange': 'NSE_INDEX',
            'interval': '5m',
            'lookback_days': 2,
            'gap_threshold_pct': 0.003, # 0.3% gap
            'risk_reward_ratio': 2.0
        }
        self.params.update(kwargs)
        self.api = APIClient()
        self.position_manager = PositionManager()
        self.has_traded_today = False
        self.last_trade_date = None

    def calculate_signal(self):
        # Only trade once per day, at the open
        current_date = datetime.now().date()
        if self.last_trade_date == current_date:
            return None, None, None, None

        df = self.api.get_history(
            symbol=self.params['symbol'],
            exchange=self.params['exchange'],
            interval=self.params['interval'],
            days=self.params['lookback_days']
        )

        if df is None or len(df) < 2:
            return None, None, None, None

        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)

        # Get daily data to find gaps
        daily_df = df.resample('D').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
        if len(daily_df) < 2:
            return None, None, None, None

        prev_close = daily_df.iloc[-2]['close']
        today_open = daily_df.iloc[-1]['open']
        gap_pct = (today_open - prev_close) / prev_close

        # Check if it's the first candle of the day
        today_data = df[df.index.date == current_date]
        if len(today_data) == 0:
            return None, None, None, None

        first_candle = today_data.iloc[0]

        # We need the first candle to be closed to check reversal
        if len(today_data) < 2:
            return None, None, None, None

        # Gap Up -> Fade it (Short)
        if gap_pct > self.params['gap_threshold_pct']:
            # Reversal Candle Check: Close < Open for Gap Up
            if first_candle['close'] < first_candle['open']:
                entry_price = today_data.iloc[-1]['close'] # Current price
                # Tighter SL based on first candle's high
                sl_price = first_candle['high']
                risk = sl_price - entry_price
                if risk <= 0: return None, None, None, None
                tp_price = entry_price - (risk * self.params['risk_reward_ratio'])

                self.last_trade_date = current_date
                return "SHORT", entry_price, sl_price, tp_price

        # Gap Down -> Fade it (Long)
        elif gap_pct < -self.params['gap_threshold_pct']:
            # Reversal Candle Check: Close > Open for Gap Down
            if first_candle['close'] > first_candle['open']:
                entry_price = today_data.iloc[-1]['close'] # Current price
                # Tighter SL based on first candle's low
                sl_price = first_candle['low']
                risk = entry_price - sl_price
                if risk <= 0: return None, None, None, None
                tp_price = entry_price + (risk * self.params['risk_reward_ratio'])

                self.last_trade_date = current_date
                return "LONG", entry_price, sl_price, tp_price

        return None, None, None, None

    def cycle(self):
        direction, entry_price, sl_price, tp_price = self.calculate_signal()

        if direction:
            qty = self.position_manager.calculate_adaptive_quantity(self.params['symbol'], sl_price=sl_price)
            self.execute_trade(
                action="SELL" if direction == "SHORT" else "BUY",
                symbol=self.params['symbol'],
                quantity=qty,
                price=entry_price,
                sl=sl_price,
                tp=tp_price,
                urgency='HIGH'
            )
            self.logger.info(f"Signal {direction} {self.params['symbol']} at {entry_price}")

if __name__ == "__main__":
    strategy = GapFadeStrategy()
    strategy.run()
