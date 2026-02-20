#!/usr/bin/env python3
"""
MCX Gold Momentum Strategy
MCX Commodity trading strategy with multi-factor analysis (RSI, EMA, ATR, Seasonality)
Refactored to use BaseStrategy.
"""
import os
import sys
import logging
import pandas as pd

# Add repo root to path
try:
    from base_strategy import BaseStrategy
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, "utils")
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy

class MCXStrategy(BaseStrategy):
    def setup(self):
        self.name = f"MCX_Gold_Momentum_{self.symbol}"

        # Strategy Parameters
        self.period_rsi = getattr(self, "period_rsi", 14)
        self.period_atr = getattr(self, "period_atr", 14)
        self.period_ema_fast = getattr(self, "period_ema_fast", 9)
        self.period_ema_slow = getattr(self, "period_ema_slow", 21)

        # Multi-Factor Arguments (passed via kwargs)
        self.usd_inr_trend = getattr(self, "usd_inr_trend", "Neutral")
        self.usd_inr_volatility = getattr(self, "usd_inr_volatility", 0.0)
        self.seasonality_score = getattr(self, "seasonality_score", 50)
        self.global_alignment_score = getattr(self, "global_alignment_score", 50)

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--period_ema_fast", type=int, default=9, help="Fast EMA Period")
        parser.add_argument("--period_ema_slow", type=int, default=21, help="Slow EMA Period")

        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

    def cycle(self):
        """Main execution cycle"""
        # Fetch Data
        df = self.fetch_history(days=5, interval="15m", exchange="MCX")
        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}.")
            return

        # Indicators
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
        df["ema_fast"] = self.calculate_ema(df["close"], period=self.period_ema_fast)
        df["ema_slow"] = self.calculate_ema(df["close"], period=self.period_ema_slow)
        df["atr"] = self.calculate_atr_series(df, period=self.period_atr) # Use series for plotting/logging if needed

        current = df.iloc[-1]

        # Logic
        has_position = self.pm.has_position() if self.pm else False

        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        base_qty = self.quantity
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size.")
            base_qty = max(1, int(base_qty * 0.7))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Condition: Fast EMA > Slow EMA AND RSI > 55
        entry_condition = (current["ema_fast"] > current["ema_slow"]) and (current["rsi"] > 55)

        if not has_position:
            if entry_condition:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.buy(base_qty, current['close'])

        # Exit Logic
        elif has_position:
            # Condition: Fast EMA < Slow EMA OR RSI < 40
            exit_condition = (current["ema_fast"] < current["ema_slow"]) or (current["rsi"] < 40)

            if exit_condition:
                self.logger.info(f"EXIT SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.sell(abs(self.pm.position), current['close'])

    def get_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty: return "HOLD", 0.0, {}

        # Indicators
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
        df["ema_fast"] = self.calculate_ema(df["close"], period=self.period_ema_fast)
        df["ema_slow"] = self.calculate_ema(df["close"], period=self.period_ema_slow)

        current = df.iloc[-1]
        entry_condition = (current["ema_fast"] > current["ema_slow"]) and (current["rsi"] > 55)

        if entry_condition:
            return "BUY", 1.0, {"rsi": current["rsi"], "ema_fast": current["ema_fast"]}

        return "HOLD", 0.0, {}

# Module level wrapper for backtesting compatibility
def generate_signal(df, client=None, symbol=None, params=None):
    return MCXStrategy.backtest_signal(df, params)

if __name__ == "__main__":
    MCXStrategy.cli()
