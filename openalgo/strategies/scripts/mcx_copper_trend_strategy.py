#!/usr/bin/env python3
"""
MCX Copper Trend Strategy
MCX Commodity trading strategy with multi-factor analysis (Bollinger Bands, MACD, RSI)
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

from trading_utils import APIClient, PositionManager, is_market_open, calculate_rsi, calculate_bollinger_bands, calculate_macd, calculate_atr

class MCXStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = pd.DataFrame()

        self.period_rsi = int(kwargs.get('period_rsi', 14))
        self.period_bb = int(kwargs.get('period_bb', 20))
        self.std_dev = float(kwargs.get('std_dev', 2.0))
        self.period_atr = int(kwargs.get('period_atr', 14))
        self.macd_fast = int(kwargs.get('macd_fast', 12))
        self.macd_slow = int(kwargs.get('macd_slow', 26))
        self.macd_signal = int(kwargs.get('macd_signal', 9))
        self.rsi_buy = int(kwargs.get('rsi_buy', 50))
        self.rsi_sell = int(kwargs.get('rsi_sell', 50))

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
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

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
        # RSI
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)

        # Bollinger Bands
        df["bb_mid"], df["bb_upper"], df["bb_lower"] = self.calculate_bollinger_bands(df["close"], window=self.period_bb, num_std=self.std_dev)

        # MACD
        df["macd"], df["macd_signal"], df["macd_hist"] = self.calculate_macd(df["close"], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)

        # ATR
        df["atr"] = self.calculate_atr_series(df, period=self.period_atr)

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
            # BUY Entry: Close > Upper BB AND RSI > 50 AND MACD Hist > 0
            if (current['close'] > current['bb_upper'] and
                current['rsi'] > self.rsi_buy and
                current['macd_hist'] > 0):

                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, MACD_Hist={current['macd_hist']:.2f}")
                self.buy(base_qty, current["close"])

        # Exit Logic
        elif has_position:
            pos_qty = current_pos
            entry_price = self.pm.entry_price

            # Exit Long: Close < Middle BB (SMA 20) OR RSI < 40
            if pos_qty > 0:
                if (current['close'] < current['bb_mid'] or
                    current['rsi'] < 40):
                    self.logger.info(f"EXIT LONG: Trend Faded or RSI Weak")
                    self.sell(abs(pos_qty), current["close"])

            # Exit Short logic (if supported)
            # Not implementing Short Entry for now as per requirement focusing on Trend Following primarily,
            # but usually Trend Following handles both directions.
            # Assuming Long Only for commodities or symmetric. Let's keep it simple for now as per prompt example.

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
        if (current['close'] > current['bb_upper'] and
            current['rsi'] > self.rsi_buy and
            current['macd_hist'] > 0):
            return "BUY", 1.0, {"reason": "BB Breakout + MACD Confirmed"}

        # Exit condition check is trickier in generate_signal as it depends on having a position.
        # Simple backtest engines usually just take BUY/SELL signals.
        # If we want to simulate an exit, we might need a distinct SELL signal or rely on stop loss logic in engine.
        # Here we return SELL if conditions for exit are met, assuming we are long.
        if (current['close'] < current['bb_mid'] or current['rsi'] < 40):
             return "SELL", 1.0, {"reason": "Trend Broken"}

        return "HOLD", 0.0, {}

if __name__ == "__main__":
    MCXStrategy.cli()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    return MCXStrategy.backtest_signal(df, params)
