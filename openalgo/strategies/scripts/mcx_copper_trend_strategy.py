#!/usr/bin/env python3
"""
MCX Copper Trend Strategy
MCX Commodity trading strategy with multi-factor analysis (Bollinger Bands, MACD, RSI)
"""
import os
import sys

# Add repo root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
sys.path.insert(0, utils_dir)

from base_strategy import BaseStrategy

class MCXCopperTrendStrategy(BaseStrategy):
    def setup(self):
        self.interval = '15m'
        self.exchange = 'MCX'

        if self.symbol:
            self.name = f"MCX_Copper_Trend_{self.symbol}"

        # Strategy Parameters
        self.period_rsi = int(getattr(self, 'period_rsi', 14))
        self.period_bb = int(getattr(self, 'period_bb', 20))
        self.std_dev = float(getattr(self, 'std_dev', 2.0))
        self.period_atr = int(getattr(self, 'period_atr', 14))
        self.macd_fast = int(getattr(self, 'macd_fast', 12))
        self.macd_slow = int(getattr(self, 'macd_slow', 26))
        self.macd_signal = int(getattr(self, 'macd_signal', 9))
        self.rsi_buy = int(getattr(self, 'rsi_buy', 50))
        self.rsi_sell = int(getattr(self, 'rsi_sell', 50))

        # Multi-Factor Parameters
        self.usd_inr_volatility = float(getattr(self, 'usd_inr_volatility', 0.0))
        self.seasonality_score = int(getattr(self, 'seasonality_score', 50))
        self.global_alignment_score = int(getattr(self, 'global_alignment_score', 50))

        # Declarative Indicators Configuration for BaseStrategy automation
        self.indicators = {
            'rsi': self.period_rsi,
            'bollinger': (self.period_bb, self.std_dev),
            'macd': (self.macd_fast, self.macd_slow, self.macd_signal),
            'atr': self.period_atr,
            'sma': [20]  # Used as bb_mid
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
        parser.add_argument("--period_bb", type=int, default=20, help="Bollinger Band Period")
        parser.add_argument("--std_dev", type=float, default=2.0, help="Bollinger Band Std Dev")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--macd_fast", type=int, default=12, help="MACD Fast Period")
        parser.add_argument("--macd_slow", type=int, default=26, help="MACD Slow Period")
        parser.add_argument("--macd_signal", type=int, default=9, help="MACD Signal Period")
        parser.add_argument("--rsi_buy", type=int, default=50, help="RSI Buy Threshold")
        parser.add_argument("--rsi_sell", type=int, default=50, help="RSI Sell Threshold")

    def get_signal(self, df):
        """
        Generate signal using pre-calculated indicators.
        Returns: ('BUY'/'SELL'/'EXIT'/'HOLD', quantity [optional], details [optional])
        """
        if df.empty or len(df) < max(self.macd_slow, self.period_rsi, self.period_bb, self.period_atr) + 5:
            return 'HOLD', 0.0, {}

        current = df.iloc[-1]

        # Calculate MACD Histogram explicitly
        macd_hist = current["macd"] - current["signal"]

        details = {
            "rsi": current["rsi"],
            "macd": current["macd"],
            "macd_hist": macd_hist,
            "bb_upper": current["upper_band"],
            "bb_mid": current["sma_20"]
        }

        # BUY Entry: Close > Upper BB AND RSI > 50 AND MACD Hist > 0
        if (current['close'] > current['upper_band'] and
            current['rsi'] > self.rsi_buy and
            macd_hist > 0):
            return "BUY", 1.0, details

        # Exit condition: Close < Middle BB (SMA 20) OR RSI < 40
        if (current['close'] < current['sma_20'] or current['rsi'] < 40):
             return "EXIT", 1.0, details

        return "HOLD", 0.0, {}

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

        if not has_position and signal == 'BUY':
             self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, MACD_Hist={details['macd_hist']:.2f}")
             self.execute_trade('BUY', base_qty, current['close'])

        elif has_position and signal == 'EXIT':
             reason = "Trend Faded or RSI Weak"
             self.logger.info(f"EXIT: {reason}. Price={current['close']}, RSI={current['rsi']:.2f}")
             pos_qty = self.pm.position
             self.execute_trade('SELL' if pos_qty > 0 else 'BUY', abs(pos_qty), current['close'])


# Backtesting support
generate_signal = MCXCopperTrendStrategy.backtest_signal

if __name__ == "__main__":
    MCXCopperTrendStrategy.cli()
