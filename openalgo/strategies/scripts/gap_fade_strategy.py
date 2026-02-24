"""
Gap Fade Strategy
Fades gaps (Gap Up -> Sell, Gap Down -> Buy) if confirmed by Reversal Candle.
Includes ADX and RSI filters and strict Stop Loss.
"""
import pandas as pd
from strategy_preamble import BaseStrategy

class GapFadeStrategy(BaseStrategy):
    def setup(self):
        if self.symbol:
            self.name = f"GapFade_{self.symbol}"

        # Parameters
        self.adx_period = getattr(self, "adx_period", 14)
        self.adx_threshold = getattr(self, "adx_threshold", 25) # Max ADX for range-bound
        self.rsi_period = getattr(self, "rsi_period", 14)
        self.rsi_overbought = getattr(self, "rsi_overbought", 60)
        self.rsi_oversold = getattr(self, "rsi_oversold", 40)

        # Risk
        self.sl_multiplier = getattr(self, "sl_multiplier", 2.0) # 2 * ATR
        self.risk_pct = getattr(self, "risk_pct", 1.0)

        self.trailing_stop = 0.0
        self.atr = 0.0

    def cycle(self):
        # Fetch Data
        df = self.fetch_and_prepare_data(days=5, min_rows=50)
        if df is None: return

        # Indicators
        self.atr = self.calculate_atr(df)
        df['adx'] = self.calculate_adx_series(df, period=self.adx_period)
        df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)

        last = df.iloc[-1]

        # Check Gap (Open vs Previous Close)
        # Let's get Daily data for Gap detection
        daily_df = self.fetch_history(days=5, interval="1d")

        gap_up = False
        gap_down = False

        if not daily_df.empty and len(daily_df) >= 2:
            today_open = daily_df.iloc[-1]['open']
            prev_close = daily_df.iloc[-2]['close']

            gap_up = today_open > prev_close * 1.002 # 0.2% gap
            gap_down = today_open < prev_close * 0.998

        # Reversal Candle logic on current timeframe (e.g. 5m)
        is_bearish_reversal = last['close'] < last['open']
        is_bullish_reversal = last['close'] > last['open']

        # Filters
        adx = last['adx']
        rsi = last['rsi']

        is_range_bound = adx < self.adx_threshold

        if self.pm and self.pm.has_position():
            # Exit Logic
            if self.trailing_stop != 0:
                 if (self.pm.position > 0 and last['close'] < self.trailing_stop) or \
                    (self.pm.position < 0 and last['close'] > self.trailing_stop):
                     self.execute_trade("EXIT", abs(self.pm.position), last['close'])
                     self.trailing_stop = 0.0
        else:
            # Entry Logic
            if is_range_bound:
                if gap_up and is_bearish_reversal and rsi > self.rsi_overbought:
                     qty = self.get_adaptive_quantity(last['close'], self.risk_pct)
                     self.execute_trade("SELL", qty, last['close'])
                     self.trailing_stop = last['high'] + (self.atr * 0.5) # Tight stop above high
                     self.logger.info(f"Gap Fade SELL: Price {last['close']}, ADX {adx:.2f}, RSI {rsi:.2f}")

                elif gap_down and is_bullish_reversal and rsi < self.rsi_oversold:
                     qty = self.get_adaptive_quantity(last['close'], self.risk_pct)
                     self.execute_trade("BUY", qty, last['close'])
                     self.trailing_stop = last['low'] - (self.atr * 0.5) # Tight stop below low
                     self.logger.info(f"Gap Fade BUY: Price {last['close']}, ADX {adx:.2f}, RSI {rsi:.2f}")

    def get_signal(self, df):
        # Backtest implementation
        if df.empty: return 'HOLD', 0.0, {}

        # Indicators
        atr = self.calculate_atr(df)
        adx = self.calculate_adx(df, period=self.adx_period)
        rsi = self.calculate_rsi(df['close'], period=self.rsi_period).iloc[-1]

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Gap Detection (Approximation using previous close vs current open)
        gap_up = last['open'] > prev['close'] * 1.002
        gap_down = last['open'] < prev['close'] * 0.998

        is_bearish_reversal = last['close'] < last['open']
        is_bullish_reversal = last['close'] > last['open']

        is_range_bound = adx < self.adx_threshold

        details = {'adx': adx, 'rsi': rsi, 'gap_up': gap_up, 'gap_down': gap_down}

        if is_range_bound:
            if gap_up and is_bearish_reversal and rsi > self.rsi_overbought:
                return 'SELL', 1.0, details
            elif gap_down and is_bullish_reversal and rsi < self.rsi_oversold:
                return 'BUY', 1.0, details

        return 'HOLD', 0.0, details

# Wrapper
generate_signal = GapFadeStrategy.backtest_signal

if __name__ == "__main__":
    GapFadeStrategy.cli()
