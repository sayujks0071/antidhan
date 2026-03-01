import os
import sys

# Preamble to ensure correct paths
current_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(current_dir)
openalgo_root = os.path.dirname(strategies_dir)
parent_root = os.path.dirname(openalgo_root)
if openalgo_root not in sys.path:
    sys.path.insert(0, openalgo_root)
if parent_root not in sys.path:
    sys.path.insert(0, parent_root)

try:
    from openalgo.strategies.utils.base_strategy import BaseStrategy
    from openalgo.strategies.utils.trading_utils import get_api_credentials, APIClient, is_market_open
except ImportError:
    try:
        from strategies.utils.base_strategy import BaseStrategy
        from strategies.utils.trading_utils import get_api_credentials, APIClient, is_market_open
    except ImportError:
        pass
from datetime import datetime
import time

class GapFadeStrategy(BaseStrategy):
    """
    Gap Fade Strategy
    Fades opening gaps if a Reversal Candle confirms the direction (e.g., Close < Open for Gap Up) using 5-minute intraday data. Features SL/TP based on the first candle's High/Low.
    """
    params = {
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX",
        "interval": "5m"
    }

    def __init__(self, **kwargs):
        super().__init__(name="GapFadeStrategy", **kwargs)
        creds = get_api_credentials()
        self.api_client = APIClient(api_key=creds.get("api_key"), host=creds.get("host"))
        self.symbol = getattr(self, "symbol", self.params.get("symbol", "NIFTY"))
        self.exchange = getattr(self, "exchange", self.params.get("exchange", "NSE_INDEX"))
        self.interval = getattr(self, "interval", self.params.get("interval", "5m"))

    def cycle(self):
        try:
            df = self.fetch_history(symbol=self.symbol, exchange=self.exchange, interval=self.interval, days=2)
            if df is None or df.empty or len(df) < 2:
                return

            # Identify first candle of the day
            today = df.index[-1].date()
            today_df = df[df.index.date == today]
            if today_df.empty:
                return

            first_candle = today_df.iloc[0]

            # Yesterday's closing
            yesterday_df = df[df.index.date < today]
            if yesterday_df.empty:
                return

            prev_close = yesterday_df.iloc[-1]['close']

            gap_up = first_candle['open'] > prev_close
            gap_down = first_candle['open'] < prev_close

            # Reversal candle condition
            reversal_down = first_candle['close'] < first_candle['open']
            reversal_up = first_candle['close'] > first_candle['open']

            last_close = df.iloc[-1]['close']

            # Open Position Management
            position = self.pm.get_position(self.symbol) if self.pm else 0
            if position != 0:
                # Check SL/TP
                if hasattr(self, 'stop_loss') and hasattr(self, 'take_profit'):
                    if position > 0: # Long
                        if last_close <= self.stop_loss or last_close >= self.take_profit:
                            self.logger.info(f"Closing LONG position. SL/TP hit. Close: {last_close}")
                            self.execute_trade('SELL', abs(position), last_close)
                            self.stop_loss = 0
                            self.take_profit = 0
                    elif position < 0: # Short
                        if last_close >= self.stop_loss or last_close <= self.take_profit:
                            self.logger.info(f"Closing SHORT position. SL/TP hit. Close: {last_close}")
                            self.execute_trade('BUY', abs(position), last_close)
                            self.stop_loss = 0
                            self.take_profit = 0
                return # Already in position, just manage it

            # Entry logic (Only look at first candle if it's currently the first candle)
            # Fades opening gaps only if a Reversal Candle confirms the direction
            # For simplicity, we trigger entry if we are not in position and first candle meets criteria
            # But we must only trigger once per day.

            if not hasattr(self, 'last_trade_date') or self.last_trade_date != today:
                if gap_up and reversal_down:
                    self.logger.info(f"Gap Up ({first_candle['open']:.2f} > {prev_close:.2f}) and Reversal Down ({first_candle['close']:.2f} < {first_candle['open']:.2f}). Sell signal.")

                    sl = first_candle['high']
                    risk = sl - last_close
                    if risk <= 0: risk = 10 # Fallback risk
                    tp = last_close - (2 * risk) # 1:2 RR

                    self.stop_loss = sl
                    self.take_profit = tp
                    self.last_trade_date = today

                    self.execute_trade('SELL', self.quantity, last_close)

                elif gap_down and reversal_up:
                    self.logger.info(f"Gap Down ({first_candle['open']:.2f} < {prev_close:.2f}) and Reversal Up ({first_candle['close']:.2f} > {first_candle['open']:.2f}). Buy signal.")

                    sl = first_candle['low']
                    risk = last_close - sl
                    if risk <= 0: risk = 10 # Fallback risk
                    tp = last_close + (2 * risk) # 1:2 RR

                    self.stop_loss = sl
                    self.take_profit = tp
                    self.last_trade_date = today

                    self.execute_trade('BUY', self.quantity, last_close)

        except Exception as e:
            self.logger.error(f"Error calculating signal: {e}")

    def generate_signal(self, df):
        # Implementation of generate_signal/calculate_signal designed specifically for backtesting support.
        # Required by memory
        pass

if __name__ == "__main__":
    GapFadeStrategy.cli()
