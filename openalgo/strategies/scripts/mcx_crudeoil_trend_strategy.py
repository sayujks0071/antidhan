#!/usr/bin/env python3
"""
MCX Crude Oil Trend Strategy
MCX Commodity trading strategy with EMA, RSI, and ATR analysis
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

from trading_utils import APIClient, PositionManager, is_market_open, calculate_rsi, calculate_atr, calculate_ema

class MCXStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = pd.DataFrame()

        self.period_rsi = int(kwargs.get('period_rsi', 14))
        self.period_atr = int(kwargs.get('period_atr', 14))
        self.period_ema = int(kwargs.get('period_ema', 20))
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

        # Calculate indicators
        df["rsi"] = self.calculate_rsi(df["close"], self.period_rsi)
        df["atr"] = self.calculate_atr_series(df, self.period_atr)
        df["ema_fast"] = self.calculate_ema(df["close"], self.period_ema)

        self.data = df

    def cycle(self):
        """Check entry and exit conditions"""
        self.fetch_data()
        self.calculate_indicators()

        if self.data.empty or len(self.data) < 50:
            return

        current = self.data.iloc[-1]

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        base_qty = 1
        if self.pm:
            # Use Adaptive Sizing (Monthly ATR favored)
            try:
                base_qty = self.get_adaptive_quantity(current["close"])
                self.logger.info(f"Adaptive Quantity Calculated: {base_qty}")
            except Exception as e:
                self.logger.error(f"Adaptive sizing failed: {e}. Defaulting to 1.")
                base_qty = 1

        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7)) # Valid only if base > 1, but keeps logic

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic
        # Buy: Close > EMA AND RSI > 50
        buy_signal = (current["close"] > current["ema_fast"]) and (current["rsi"] > 50)
        # Sell: Close < EMA AND RSI < 50
        sell_signal = (current["close"] < current["ema_fast"]) and (current["rsi"] < 50)

        if not has_position:
            if buy_signal:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.buy(base_qty, current["close"])
            elif sell_signal:
                self.logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.sell(base_qty, current["close"])

        # Exit Logic
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
                elif (current["close"] < current["ema_fast"]): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"
            elif pos_qty < 0: # Short
                if (current["close"] <= entry_price - target):
                    exit_signal = True
                    reason = "Target Hit"
                elif (current["close"] >= entry_price + stop):
                    exit_signal = True
                    reason = "Stop Loss Hit"
                elif (current["close"] > current["ema_fast"]): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"

            if exit_signal:
                self.logger.info(f"EXIT: {reason}")
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

        buy_signal = (current["close"] > current["ema_fast"]) and (current["rsi"] > 50)
        sell_signal = (current["close"] < current["ema_fast"]) and (current["rsi"] < 50)

        if buy_signal:
            return "BUY", 1.0, {"reason": "Trend Long"}
        elif sell_signal:
            return "SELL", 1.0, {"reason": "Trend Short"}

        return "HOLD", 0.0, {}

if __name__ == "__main__":
    MCXStrategy.cli()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    return MCXStrategy.backtest_signal(df, params)
