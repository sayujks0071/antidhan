#!/usr/bin/env python3
"""
MCX Silver Trend Strategy
MCX Commodity trading strategy with multi-factor analysis (EMA, RSI, ADX)
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

from trading_utils import APIClient, PositionManager, is_market_open, calculate_rsi, calculate_atr, calculate_adx, calculate_ema

class MCXStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = pd.DataFrame()

        self.period_rsi = int(kwargs.get('period_rsi', 14))
        self.period_atr = int(kwargs.get('period_atr', 14))
        self.period_adx = int(kwargs.get('period_adx', 14))
        self.period_ema_fast = int(kwargs.get('period_ema_fast', 20))
        self.period_ema_slow = int(kwargs.get('period_ema_slow', 50))
        self.rsi_buy = int(kwargs.get('rsi_buy', 55))
        self.rsi_sell = int(kwargs.get('rsi_sell', 45))
        self.adx_threshold = int(kwargs.get('adx_threshold', 25))

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
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d") # Increased lookback for EMA 50

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

        # Calculate indicators using trading_utils
        df['rsi'] = self.calculate_rsi(df['close'], period=self.period_rsi)
        df['atr'] = self.calculate_atr_series(df, period=self.period_atr)
        df['adx'] = self.calculate_adx_series(df, period=self.period_adx)
        df['ema_fast'] = self.calculate_ema(df['close'], period=self.period_ema_fast)
        df['ema_slow'] = self.calculate_ema(df['close'], period=self.period_ema_slow)

        self.data = df.fillna(0)

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
            # Reload state to be safe
            self.pm.load_state()
            current_pos = self.pm.position
        else:
            current_pos = 0

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        base_qty = 1
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic
        if not has_position:
            # BUY Entry: Close > EMA Fast > EMA Slow, RSI > 55, ADX > 25
            if (current['close'] > current['ema_fast'] > current['ema_slow'] and
                current['rsi'] > self.rsi_buy and
                current['adx'] > self.adx_threshold):

                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                self.buy(base_qty, current["close"])

            # SELL Entry: Close < EMA Fast < EMA Slow, RSI < 45, ADX > 25
            elif (current['close'] < current['ema_fast'] < current['ema_slow'] and
                  current['rsi'] < self.rsi_sell and
                  current['adx'] > self.adx_threshold):

                self.logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                self.sell(base_qty, current["close"])

        # Exit Logic
        elif has_position:
            pos_qty = current_pos
            entry_price = self.pm.entry_price

            # Exit Long: Trend Reversal (Close < EMA Fast)
            if pos_qty > 0:
                if current['close'] < current['ema_fast']:
                    self.logger.info(f"EXIT LONG: Trend Faded (Price < EMA Fast)")
                    self.sell(abs(pos_qty), current["close"])

            # Exit Short: Trend Reversal (Close > EMA Fast)
            elif pos_qty < 0:
                if current['close'] > current['ema_fast']:
                    self.logger.info(f"EXIT SHORT: Trend Faded (Price > EMA Fast)")
                    self.buy(abs(pos_qty), current["close"])

    def get_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        self.data = df
        self.calculate_indicators()

        if len(self.data) < 2:
            return "HOLD", 0.0, {}

        current = self.data.iloc[-1]

        # Signal Logic
        if (current['close'] > current['ema_fast'] > current['ema_slow'] and
            current['rsi'] > self.rsi_buy and
            current['adx'] > self.adx_threshold):
            return "BUY", 1.0, {"reason": "Trend Strong + Momentum"}

        elif (current['close'] < current['ema_fast'] < current['ema_slow'] and
              current['rsi'] < self.rsi_sell and
              current['adx'] > self.adx_threshold):
            return "SELL", 1.0, {"reason": "Trend Weak + Momentum"}

        return "HOLD", 0.0, {}

if __name__ == "__main__":
    MCXStrategy.cli()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    return MCXStrategy.backtest_signal(df, params)
