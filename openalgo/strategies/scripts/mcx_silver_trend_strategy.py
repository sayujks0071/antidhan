#!/usr/bin/env python3
"""
MCX Silver Trend Strategy
MCX Commodity trading strategy with multi-factor analysis (EMA, RSI, ADX)
"""
import os
import sys

# Add repo root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
sys.path.insert(0, utils_dir)

from base_strategy import BaseStrategy

class MCXSilverTrendStrategy(BaseStrategy):
    def setup(self):
        self.interval = '15m'
        self.exchange = 'MCX'

        if self.symbol:
            self.name = f"MCX_Silver_Trend_{self.symbol}"

        # Strategy Parameters
        self.period_rsi = int(getattr(self, 'period_rsi', 14))
        self.period_atr = int(getattr(self, 'period_atr', 14))
        self.period_adx = int(getattr(self, 'period_adx', 14))
        self.period_ema_fast = int(getattr(self, 'period_ema_fast', 20))
        self.period_ema_slow = int(getattr(self, 'period_ema_slow', 50))
        self.rsi_buy = int(getattr(self, 'rsi_buy', 55))
        self.rsi_sell = int(getattr(self, 'rsi_sell', 45))
        self.adx_threshold = int(getattr(self, 'adx_threshold', 25))

        # Multi-Factor Parameters
        self.usd_inr_volatility = float(getattr(self, 'usd_inr_volatility', 0.0))
        self.seasonality_score = int(getattr(self, 'seasonality_score', 50))
        self.global_alignment_score = int(getattr(self, 'global_alignment_score', 50))

        # Declarative Indicators Configuration for BaseStrategy automation
        self.indicators = {
            'rsi': self.period_rsi,
            'atr': self.period_atr,
            'adx': self.period_adx,
            'ema': [self.period_ema_fast, self.period_ema_slow]
        }

    @classmethod
    def add_arguments(cls, parser):
        # Multi-Factor Arguments
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

        # Strategy Parameters
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--period_adx", type=int, default=14, help="ADX Period")
        parser.add_argument("--period_ema_fast", type=int, default=20, help="EMA Fast Period")
        parser.add_argument("--period_ema_slow", type=int, default=50, help="EMA Slow Period")
        parser.add_argument("--rsi_buy", type=int, default=55, help="RSI Buy Threshold")
        parser.add_argument("--rsi_sell", type=int, default=45, help="RSI Sell Threshold")
        parser.add_argument("--adx_threshold", type=int, default=25, help="ADX Threshold")

    def get_signal(self, df):
        """
        Generate signal using pre-calculated indicators.
        Returns: ('BUY'/'SELL'/'EXIT'/'HOLD', quantity [optional], details [optional])
        """
        if df.empty or len(df) < max(self.period_ema_slow, self.period_rsi, self.period_atr, self.period_adx) + 5:
            return 'HOLD', 0.0, {}

        current = df.iloc[-1]

        ema_fast_col = f"ema_{self.period_ema_fast}"
        ema_slow_col = f"ema_{self.period_ema_slow}"

        details = {
            "rsi": current["rsi"],
            "adx": current["adx"],
            "ema_fast": current[ema_fast_col],
            "ema_slow": current[ema_slow_col]
        }

        # BUY Entry: Close > EMA Fast > EMA Slow, RSI > 55, ADX > 25
        if (current['close'] > current[ema_fast_col] > current[ema_slow_col] and
            current['rsi'] > self.rsi_buy and
            current['adx'] > self.adx_threshold):
            return "BUY", 1.0, details

        # SELL Entry: Close < EMA Fast < EMA Slow, RSI < 45, ADX > 25
        if (current['close'] < current[ema_fast_col] < current[ema_slow_col] and
            current['rsi'] < self.rsi_sell and
            current['adx'] > self.adx_threshold):
            return "SELL", 1.0, details

        return "HOLD", 0.0, details

    def cycle(self):
        """Check entry and exit conditions"""
        df = self.fetch_and_prepare_data(days=10, min_rows=50, exchange=self.exchange)

        if df is None:
            return

        df = self.calculate_indicators(df)
        current = df.iloc[-1]

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        base_qty = 1
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(round(base_qty * 0.7)))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        signal, qty, details = self.get_signal(df)

        ema_fast_col = f"ema_{self.period_ema_fast}"
        ema_slow_col = f"ema_{self.period_ema_slow}"

        if not has_position:
            if signal == 'BUY':
                 self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                 self.execute_trade('BUY', base_qty, current['close'])
            elif signal == 'SELL':
                 self.logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                 self.execute_trade('SELL', base_qty, current['close'])

        elif has_position:
            pos_qty = self.pm.position

            # Exit Long: Trend Reversal (Close < EMA Fast)
            if pos_qty > 0:
                if current['close'] < current[ema_fast_col]:
                    self.logger.info(f"EXIT LONG: Trend Faded (Price < EMA Fast)")
                    self.execute_trade('SELL', abs(pos_qty), current['close'])

            # Exit Short: Trend Reversal (Close > EMA Fast)
            elif pos_qty < 0:
                if current['close'] > current[ema_fast_col]:
                    self.logger.info(f"EXIT SHORT: Trend Faded (Price > EMA Fast)")
                    self.execute_trade('BUY', abs(pos_qty), current['close'])

# Backtesting support
generate_signal = MCXSilverTrendStrategy.backtest_signal

if __name__ == "__main__":
    MCXSilverTrendStrategy.cli()
