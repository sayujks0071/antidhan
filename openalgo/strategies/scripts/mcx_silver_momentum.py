#!/usr/bin/env python3
"""
MCX Silver Momentum Strategy
MCX Commodity trading strategy with RSI, ATR, and SMA analysis.
Refactored to inherit from BaseStrategy (DRY) and use strategy_preamble.
"""
import strategy_preamble
from base_strategy import BaseStrategy
import pandas as pd

class MCXSilverMomentumStrategy(BaseStrategy):
    def setup(self):
        """Initialize strategy parameters and indicators."""
        self.period_rsi = int(getattr(self, "period_rsi", 14))
        self.period_atr = int(getattr(self, "period_atr", 14))
        self.seasonality_score = int(getattr(self, "seasonality_score", 50))
        self.usd_inr_volatility = float(getattr(self, "usd_inr_volatility", 0.0))

        # Declarative Indicators
        self.indicators = {
            'rsi': self.period_rsi,
            'atr': self.period_atr,
            'sma': 50
        }

    @classmethod
    def add_arguments(cls, parser):
        """Add custom arguments for this strategy."""
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")

    def generate_signal(self, df):
        """
        Generate signal for BaseStrategy cycle.
        Returns: ("BUY"/"SELL"/"EXIT"/"HOLD", qty, details) or just Signal String.
        """
        if df.empty:
            return "HOLD"

        current = df.iloc[-1]
        close = current['close']

        # Check if indicators exist
        if 'sma_50' not in current or 'rsi' not in current or 'atr' not in current:
             self.logger.warning("Indicators missing in dataframe.")
             return "HOLD"

        sma_50 = current['sma_50']
        rsi = current['rsi']
        atr = current['atr']

        # Context Filters
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 0.8

        if usd_vol_high:
            self.logger.warning(f"High USD/INR Volatility ({self.usd_inr_volatility}). Trading restricted.")
            if self.usd_inr_volatility > 1.5:
                return "HOLD"

        has_position = False
        pos_qty = 0
        entry_price = 0.0

        if self.pm:
            has_position = self.pm.has_position()
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price

        # Exit Logic
        if has_position:
            is_long = pos_qty > 0
            stop_loss_dist = 2 * atr
            take_profit_dist = 4 * atr

            exit_reason = ""
            should_exit = False

            if is_long:
                if close < (entry_price - stop_loss_dist):
                    should_exit = True; exit_reason = "Stop Loss"
                elif close > (entry_price + take_profit_dist):
                    should_exit = True; exit_reason = "Take Profit"
                elif close < sma_50 or rsi < 40:
                    should_exit = True; exit_reason = "Trend Reversal"
            else: # Short
                if close > (entry_price + stop_loss_dist):
                    should_exit = True; exit_reason = "Stop Loss"
                elif close < (entry_price - take_profit_dist):
                    should_exit = True; exit_reason = "Take Profit"
                elif close > sma_50 or rsi > 60:
                    should_exit = True; exit_reason = "Trend Reversal"

            if should_exit:
                self.logger.info(f"Signal: EXIT ({exit_reason})")
                return "EXIT"

        # Entry Logic
        elif not has_position:
            if not seasonality_ok:
                self.logger.info("Seasonality Weak: Skipping new entries.")
                return "HOLD"

            # BUY
            if close > sma_50 and rsi > 55:
                self.logger.info(f"Signal: BUY. Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                return "BUY"

            # SELL
            elif close < sma_50 and rsi < 45:
                self.logger.info(f"Signal: SELL. Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                return "SELL"

        return "HOLD"

    def get_signal(self, df):
        """Backtesting interface."""
        signal = self.generate_signal(df)
        if isinstance(signal, str):
            return signal, self.quantity, {}
        return "HOLD", 0, {}

if __name__ == "__main__":
    MCXSilverMomentumStrategy.cli()
