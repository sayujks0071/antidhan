#!/usr/bin/env python3
"""
MCX Crude Oil Trend Strategy
MCX Commodity trading strategy with EMA, RSI, and ATR analysis
"""
import os
import sys

# Add repo root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
sys.path.insert(0, utils_dir)
sys.path.insert(0, os.path.dirname(strategies_dir))

from base_strategy import BaseStrategy

class MCXCrudeOilTrendStrategy(BaseStrategy):
    def setup(self):
        self.interval = '15m'
        self.exchange = 'MCX'

        if self.symbol:
            self.name = f"MCX_CrudeOil_Trend_{self.symbol}"

        # Strategy Parameters
        self.period_rsi = int(getattr(self, 'period_rsi', 14))
        self.period_atr = int(getattr(self, 'period_atr', 14))
        self.period_ema = int(getattr(self, 'period_ema', 20))

        # Multi-Factor Parameters
        self.usd_inr_volatility = float(getattr(self, 'usd_inr_volatility', 0.0))
        self.seasonality_score = int(getattr(self, 'seasonality_score', 50))
        self.global_alignment_score = int(getattr(self, 'global_alignment_score', 50))

        # Declarative Indicators Configuration
        self.indicators = {
            'rsi': self.period_rsi,
            'atr': self.period_atr,
            'ema': [self.period_ema]
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
        parser.add_argument("--period_ema", type=int, default=20, help="EMA Period")

    def get_signal(self, df):
        """
        Generate signal using pre-calculated indicators.
        Returns: ('BUY'/'SELL'/'EXIT'/'HOLD', quantity [optional], details [optional])
        """
        if df.empty or len(df) < max(self.period_ema, self.period_rsi, self.period_atr) + 5:
            return 'HOLD', 0.0, {}

        current = df.iloc[-1]
        prev = df.iloc[-2]

        ema_col = f"ema_{self.period_ema}"

        buy_signal = (current["close"] > current[ema_col]) and (current["rsi"] > 50)
        sell_signal = (current["close"] < current[ema_col]) and (current["rsi"] < 50)

        details = {
            "rsi": current["rsi"],
            "ema": current[ema_col]
        }

        # Backtesting engine will capture BUY/SELL signals
        if buy_signal:
            return "BUY", 1.0, details
        elif sell_signal:
            return "SELL", 1.0, details

        return "HOLD", 0.0, details

    def cycle(self):
        """Check entry and exit conditions"""
        df = self.fetch_and_prepare_data(days=5, min_rows=50, exchange=self.exchange)

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

        # Position sizing adjustment
        base_qty = 1
        if self.pm:
            # Use Adaptive Sizing (Monthly ATR favored)
            try:
                base_qty = self.get_adaptive_quantity(current['close'], risk_pct=1.0, capital=500000)
            except Exception as e:
                self.logger.error(f"Adaptive sizing failed: {e}. Defaulting to 1.")
                base_qty = 1

        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(round(base_qty * 0.7)))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        ema_col = f"ema_{self.period_ema}"
        buy_signal = (current["close"] > current[ema_col]) and (current["rsi"] > 50)
        sell_signal = (current["close"] < current[ema_col]) and (current["rsi"] < 50)

        if not has_position:
            if buy_signal:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.execute_trade('BUY', base_qty, current['close'])
            elif sell_signal:
                self.logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.execute_trade('SELL', base_qty, current['close'])

        elif has_position:
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price
            atr_val = current["atr"]

            # Target/Stop
            target = 2.0 * atr_val
            stop = 1.0 * atr_val

            exit_signal = False
            reason = ""

            if pos_qty > 0: # Long
                if (current["close"] >= entry_price + target):
                    exit_signal = True
                    reason = "Target Hit"
                elif (current["close"] <= entry_price - stop):
                    exit_signal = True
                    reason = "Stop Loss Hit"
                elif (current["close"] < current[ema_col]): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"
            elif pos_qty < 0: # Short
                if (current["close"] <= entry_price - target):
                    exit_signal = True
                    reason = "Target Hit"
                elif (current["close"] >= entry_price + stop):
                    exit_signal = True
                    reason = "Stop Loss Hit"
                elif (current["close"] > current[ema_col]): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"

            if exit_signal:
                self.logger.info(f"EXIT: {reason}")
                self.execute_trade('SELL' if pos_qty > 0 else 'BUY', abs(pos_qty), current['close'])

# Backtesting support
generate_signal = MCXCrudeOilTrendStrategy.backtest_signal

if __name__ == "__main__":
    MCXCrudeOilTrendStrategy.cli()
