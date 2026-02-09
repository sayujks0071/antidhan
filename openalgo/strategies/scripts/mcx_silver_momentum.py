#!/usr/bin/env python3
"""
MCX Silver Momentum Strategy
MCX Commodity trading strategy with RSI, ATR, and SMA analysis.
Refactored to inherit from BaseStrategy for 30% less code and centralized management.
"""
import os
import sys
import logging
import pandas as pd
import time
from datetime import datetime, timedelta

# Add repo root to path to allow imports (if running as script)
try:
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol
except ImportError:
    # Try setting path to find utils
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol

class MCXSilverMomentum(BaseStrategy):
    def __init__(self, symbol, quantity, api_key=None, host=None, ignore_time=False,
                 log_file=None, client=None, **kwargs):
        # Default MCX parameters
        kwargs.setdefault('exchange', 'MCX')
        kwargs.setdefault('type', 'FUT')

        super().__init__(
            name=f"MCX_Momentum_{symbol}",
            symbol=symbol,
            quantity=quantity,
            api_key=api_key,
            host=host,
            ignore_time=ignore_time,
            log_file=log_file,
            client=client,
            **kwargs
        )

        # Strategy Parameters
        self.period_rsi = kwargs.get('period_rsi', 14)
        self.period_atr = kwargs.get('period_atr', 14)
        self.seasonality_score = kwargs.get('seasonality_score', 50)
        self.usd_inr_volatility = kwargs.get('usd_inr_volatility', 0.0)

        # Defaults if not provided
        self.interval = kwargs.get('interval', '15m')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")

    def cycle(self):
        """Main Strategy Logic"""

        # 1. Check Filters
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 0.8

        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Trading effectively halted or reduced.")
            if self.usd_inr_volatility > 1.5:
                self.logger.warning("Volatility too high, skipping trade.")
                return

        has_position = self.pm.has_position() if self.pm else False

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # 2. Fetch Data
        # MCX needs sufficient history for SMA50
        df = self.fetch_history(days=10, interval=self.interval)

        if df.empty or len(df) < 55:
            self.logger.warning(f"Insufficient data for {self.symbol}: {len(df)} rows.")
            return

        # 3. Indicators
        rsi_series = self.calculate_rsi(df['close'], period=self.period_rsi)
        atr_series = self.calculate_atr(df, period=self.period_atr)
        sma50_series = self.calculate_sma(df['close'], period=50)

        current = df.iloc[-1]
        close = current['close']
        rsi = rsi_series.iloc[-1]
        atr = atr_series.iloc[-1] if not isinstance(atr_series, float) else atr_series
        sma_50 = sma50_series.iloc[-1]

        # 4. Logic
        if not has_position:
            # Entry
            if close > sma_50 and rsi > 55:
                self.logger.info(f"BUY SIGNAL: Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                self.execute_trade("BUY", self.quantity, close)
            elif close < sma_50 and rsi < 45:
                self.logger.info(f"SELL SIGNAL: Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                self.execute_trade("SELL", self.quantity, close)

        else:
            # Exit
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price
            is_long = pos_qty > 0

            stop_loss_dist = 2 * atr
            take_profit_dist = 4 * atr

            exit_signal = False
            exit_reason = ""

            if is_long:
                if close < (entry_price - stop_loss_dist):
                    exit_signal = True; exit_reason = "Stop Loss"
                elif close > (entry_price + take_profit_dist):
                    exit_signal = True; exit_reason = "Take Profit"
                elif close < sma_50 or rsi < 40:
                    exit_signal = True; exit_reason = "Trend Reversal"
            else: # Short
                if close > (entry_price + stop_loss_dist):
                    exit_signal = True; exit_reason = "Stop Loss"
                elif close < (entry_price - take_profit_dist):
                    exit_signal = True; exit_reason = "Take Profit"
                elif close > sma_50 or rsi > 60:
                    exit_signal = True; exit_reason = "Trend Reversal"

            if exit_signal:
                self.logger.info(f"EXIT ({exit_reason}): Price={close}")
                self.execute_trade("SELL" if is_long else "BUY", abs(pos_qty), close)

    def generate_signal(self, df):
        """Backtesting support"""
        if df.empty: return "HOLD", 0.0, {}

        # Indicators
        df['rsi'] = self.calculate_rsi(df['close'], period=self.period_rsi)
        df['sma_50'] = self.calculate_sma(df['close'], period=50)

        current = df.iloc[-1]
        close = current['close']
        sma_50 = current['sma_50']
        rsi = current['rsi']

        if pd.isna(sma_50): return "HOLD", 0.0, {}

        if close > sma_50 and rsi > 55:
            return "BUY", 1.0, {"reason": f"Price > SMA50 & RSI({rsi:.1f}) > 55"}

        if close < sma_50 and rsi < 45:
            return "SELL", 1.0, {"reason": f"Price < SMA50 & RSI({rsi:.1f}) < 45"}

        return "HOLD", 0.0, {}

# Module level wrapper for SimpleBacktestEngine
def generate_signal(df, client=None, symbol=None, params=None):
    kwargs = params or {}
    # Create instance to access methods
    # We pass client=client so it uses the backtest client/data
    strat = MCXSilverMomentum(symbol=symbol or "TEST", quantity=1, api_key="test", host="test", client=client, **kwargs)

    # Suppress logging for backtest
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.generate_signal(df)

if __name__ == "__main__":
    MCXSilverMomentum.cli()
