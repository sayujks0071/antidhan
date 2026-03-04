#!/usr/bin/env python3
"""
MCX Aluminium Trend Strategy
MCX Commodity trading strategy with multi-factor analysis (MACD, RSI, ATR)
"""
import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

try:
    from strategy_preamble import BaseStrategy
except ImportError:
    import sys, os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
    from base_strategy import BaseStrategy

from trading_utils import APIClient, PositionManager, is_market_open

class MCXStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = pd.DataFrame()

        self.period_rsi = int(kwargs.get('period_rsi', 14))
        self.period_atr = int(kwargs.get('period_atr', 14))
        self.macd_fast = int(kwargs.get('macd_fast', 12))
        self.macd_slow = int(kwargs.get('macd_slow', 26))
        self.macd_signal = int(kwargs.get('macd_signal', 9))

        self.usd_inr_trend = kwargs.get('usd_inr_trend', 'Neutral')
        self.usd_inr_volatility = float(kwargs.get('usd_inr_volatility', 0.0))
        self.seasonality_score = int(kwargs.get('seasonality_score', 50))
        self.global_alignment_score = int(kwargs.get('global_alignment_score', 50))

        self.logger.info(f"Initialized Strategy for {self.symbol}")
        self.logger.info(f"Filters: Seasonality={self.seasonality_score}, USD_Vol={self.usd_inr_volatility}")

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--macd_fast", type=int, default=12, help="MACD Fast Period")
        parser.add_argument("--macd_slow", type=int, default=26, help="MACD Slow Period")
        parser.add_argument("--macd_signal", type=int, default=9, help="MACD Signal Period")

    def fetch_data(self):
        """Fetch live or historical data from OpenAlgo"""
        if not self.client:
            self.logger.error("API Client not initialized.")
            return

        try:
            self.logger.info(f"Fetching data for {self.symbol}...")
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

            df = self.client.history(
                symbol=self.symbol,
                interval="15m",  # MCX typically uses 5m, 15m, or 1h
                exchange="MCX",
                start_date=start_date,
                end_date=end_date,
            )

            if not df.empty and len(df) > 50:
                self.data = df
                self.logger.info(f"Fetched {len(df)} candles.")
            else:
                self.logger.warning(f"Insufficient data for {self.symbol}.")

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}", exc_info=True)

    def calculate_indicators(self):
        """Calculate technical indicators"""
        if self.data.empty:
            return

        df = self.data.copy()

        # MACD (12, 26, 9)
        # Calculate EMA Fast (12) and EMA Slow (26)
        ema_fast = df["close"].ewm(span=self.macd_fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.macd_slow, adjust=False).mean()

        df["macd_line"] = ema_fast - ema_slow
        df["macd_signal"] = df["macd_line"].ewm(span=self.macd_signal, adjust=False).mean()
        df["macd_hist"] = df["macd_line"] - df["macd_signal"]

        # RSI (14)
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period_rsi).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period_rsi).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # ATR (14)
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df["atr"] = true_range.rolling(window=self.period_atr).mean()

        self.data = df

    def cycle(self):
        """Check entry and exit conditions"""
        self.fetch_data()
        self.calculate_indicators()

        if self.data.empty or len(self.data) < 50:
            return

        current = self.data.iloc[-1]
        prev = self.data.iloc[-2]

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        global_alignment_ok = self.global_alignment_score >= 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        base_qty = 1
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7)) # Should result in 1 usually unless base is high

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic (Long)
        # MACD Line > Signal Line (Bullish Trend) AND RSI > 50 (Momentum)
        bullish_crossover = (current["macd_line"] > current["macd_signal"])
        momentum_ok = (current["rsi"] > 50)

        entry_signal = bullish_crossover and momentum_ok

        if not has_position:
            if entry_signal:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, MACD={current['macd_line']:.2f}, Signal={current['macd_signal']:.2f}")
                self.buy(base_qty, current["close"])

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position

            # Exit if MACD Line < Signal Line (Trend Reversal) OR RSI < 40 (Momentum Lost)
            trend_reversal = (current["macd_line"] < current["macd_signal"])
            momentum_lost = (current["rsi"] < 40)

            exit_signal = trend_reversal or momentum_lost

            if exit_signal:
                reason = "Trend Reversal" if trend_reversal else "Momentum Lost"
                self.logger.info(f"EXIT: {reason}. Price={current['close']}, RSI={current['rsi']:.2f}")
                if pos_qty > 0:
                    self.sell(abs(pos_qty), current["close"])
                else:
                    self.buy(abs(pos_qty), current["close"])

    def get_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        self.data = df
        self.calculate_indicators()

        current = self.data.iloc[-1]

        # MACD Line > Signal Line AND RSI > 50
        bullish_crossover = (current["macd_line"] > current["macd_signal"])
        momentum_ok = (current["rsi"] > 50)

        if bullish_crossover and momentum_ok:
            return "BUY", 1.0, {
                "reason": "signal_triggered",
                "rsi": current["rsi"],
                "macd": current["macd_line"],
                "signal": current["macd_signal"]
            }

        return "HOLD", 0.0, {}

if __name__ == "__main__":
    MCXStrategy.cli()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    return MCXStrategy.backtest_signal(df, params)
