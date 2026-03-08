import argparse
import sys
import os
import pandas as pd
import time

try:
    from openalgo.strategies.utils.base_strategy import BaseStrategy
except ImportError:
    try:
        from utils.base_strategy import BaseStrategy
    except ImportError:
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from utils.base_strategy import BaseStrategy

class GapFadeStrategy(BaseStrategy):
    """
    Gap Fade Strategy
    Fades opening gaps if a Reversal Candle confirms the direction using 2 days of 5-minute intraday data,
    and includes an ADX trend filter (< 25) and RSI confirmation (> 60 / < 40) to filter out strong trend ('Gap and Go') days.
    """

    def setup(self):
        self.interval = getattr(self, "interval", "5m")
        self.exchange = getattr(self, "exchange", "NSE")
        self.quantity = getattr(self, "quantity", 1)
        self.indicators = {
            'rsi': 14,
            'adx': 14
        }
        self.target_pct = getattr(self, "target_pct", 0.01)
        # We will use the first candle's high/low for stop loss dynamically,
        # but keep a fallback just in case
        self.stop_loss_pct_fallback = getattr(self, "stop_loss_pct", 0.005)

        self.trade_taken_today = False
        self.last_trade_date = None

        # Dynamic SL based on first candle
        self.dynamic_sl = None

    def check_new_day(self, df):
        if df.empty:
            return

        current_date = df['datetime'].iloc[-1].date()
        if self.last_trade_date != current_date:
            self.trade_taken_today = False
            self.last_trade_date = current_date
            self.dynamic_sl = None

    def get_signal(self, df):
        if len(df) < 15:
            return "HOLD", 0.0, {"reason": "Not enough data"}

        # We need the first candle of the day and the previous day's close
        df['date'] = df['datetime'].dt.date
        dates = df['date'].unique()

        if len(dates) < 2:
            return "HOLD", 0.0, {"reason": "Need at least 2 days of data"}

        current_date = dates[-1]
        prev_date = dates[-2]

        # Get previous day's close
        prev_day_data = df[df['date'] == prev_date]
        if prev_day_data.empty:
            return "HOLD", 0.0, {"reason": "No previous day data"}
        prev_close = prev_day_data['close'].iloc[-1]

        # Get current day's data
        current_day_data = df[df['date'] == current_date]
        if current_day_data.empty:
            return "HOLD", 0.0, {"reason": "No current day data"}

        # Wait for the first candle to close to assess the gap and reversal
        if len(current_day_data) < 1:
             return "HOLD", 0.0, {"reason": "Waiting for first candle to close"}

        first_candle = current_day_data.iloc[0]
        current_candle = df.iloc[-1]

        # Only trade on the exact candle after the first one, or use the first candle if we missed it
        if len(current_day_data) > 2:
             return "HOLD", 0.0, {"reason": "Too late to enter gap fade"}

        # Check if already traded today
        if self.trade_taken_today:
            return "HOLD", 0.0, {"reason": "Already traded today"}

        open_price = first_candle['open']
        gap_pct = ((open_price - prev_close) / prev_close) * 100

        # Calculate Indicators
        adx = df['adx'].iloc[-1]
        rsi = df['rsi'].iloc[-1]

        # Strong trend filter
        if adx >= 25:
             return "HOLD", 0.0, {"reason": f"Trend too strong (ADX: {adx:.2f} >= 25)"}

        # Gap Up Scenario -> Look for Short/Sell (Fade)
        if gap_pct > 0.5:
             # Reversal Candle confirmation: Close < Open for the first candle
             if first_candle['close'] < first_candle['open']:
                  # RSI Confirmation
                  if rsi > 60:
                       self.trade_taken_today = True
                       self.dynamic_sl = first_candle['high'] # SL above the high of the first candle
                       return "SELL", 1.0, {"reason": f"Fading Gap Up ({gap_pct:.2f}%), Reversal Candle confirmed, RSI: {rsi:.2f}"}

        # Gap Down Scenario -> Look for Long/Buy (Fade)
        elif gap_pct < -0.5:
             # Reversal Candle confirmation: Close > Open for the first candle
             if first_candle['close'] > first_candle['open']:
                  # RSI Confirmation
                  if rsi < 40:
                       self.trade_taken_today = True
                       self.dynamic_sl = first_candle['low'] # SL below the low of the first candle
                       return "BUY", 1.0, {"reason": f"Fading Gap Down ({gap_pct:.2f}%), Reversal Candle confirmed, RSI: {rsi:.2f}"}

        return "HOLD", 0.0, {"reason": "No gap or confirmation conditions met"}

    def generate_signal(self, df):
        self.check_new_day(df)
        signal, confidence, details = self.get_signal(df)
        return signal, self.quantity, details

    def cycle(self):
        # Fetch 2 days of 5m data
        df = self.fetch_history(days=2, interval=self.interval, exchange=self.exchange)
        if df.empty or len(df) < 50:
             return

        # Calculate Indicators
        df = self.calculate_indicators(df)

        signal, qty, details = self.generate_signal(df)
        current_price = df['close'].iloc[-1]

        if signal == "BUY":
            if not self.pm or not self.pm.has_position():
                self.logger.info(f"Signal: BUY, Reason: {details.get('reason')}")
                self.buy(qty, current_price)
        elif signal == "SELL":
             if not self.pm or not self.pm.has_position():
                 self.logger.info(f"Signal: SELL, Reason: {details.get('reason')}")
                 self.sell(qty, current_price)

        # Simple Exit Logic (Intraday or hit SL/TP)
        if self.pm and self.pm.has_position():
             pos_price = self.pm.entry_price
             # If Long
             if self.pm.position > 0:
                  sl_price = self.dynamic_sl if self.dynamic_sl is not None else pos_price * (1 - self.stop_loss_pct_fallback)
                  if current_price >= pos_price * (1 + self.target_pct) or current_price <= sl_price:
                       self.logger.info("Exiting Long Position")
                       self.sell(abs(self.pm.position), current_price)

             # If Short
             elif self.pm.position < 0:
                  sl_price = self.dynamic_sl if self.dynamic_sl is not None else pos_price * (1 + self.stop_loss_pct_fallback)
                  if current_price <= pos_price * (1 - self.target_pct) or current_price >= sl_price:
                       self.logger.info("Exiting Short Position")
                       self.buy(abs(self.pm.position), current_price)

if __name__ == "__main__":
    parser = GapFadeStrategy.get_standard_parser("Gap Fade Strategy")
    GapFadeStrategy.add_arguments(parser)
    args, unknown = parser.parse_known_args()
    kwargs = GapFadeStrategy.parse_arguments(args)

    if not kwargs.get('symbol'):
         print("Error: Must provide --symbol")
         sys.exit(1)

    strategy = GapFadeStrategy(**kwargs)
    strategy.run()