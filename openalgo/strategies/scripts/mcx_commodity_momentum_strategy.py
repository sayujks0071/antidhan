#!/usr/bin/env python3
"""
MCX Commodity Momentum Strategy
-------------------------------
A basic momentum strategy for MCX commodities (Gold, Silver, Crude Oil, etc.)
using EMA crossovers and RSI filters.

Strategy Logic:
- Entry Long: Price > EMA(20) and RSI > 50
- Entry Short: Price < EMA(20) and RSI < 50
- Exit: Target/Stop or Reversal
"""

import os
import sys
import pandas as pd
import numpy as np
import logging
from datetime import datetime

# Setup Logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger("MCX_Momentum")

class MCXMomentumStrategy:
    def __init__(self, symbol, timeframe="15minute"):
        self.symbol = symbol
        self.timeframe = timeframe

        # Strategy Parameters
        self.ema_period = 20
        self.rsi_period = 14
        self.rsi_upper = 60
        self.rsi_lower = 40
        self.stop_loss_pct = 0.01
        self.target_pct = 0.02

        # Enhanced Parameters (Placeholders for Advanced Strategy to inject)
        self.usd_inr_factor = 1.0
        self.global_correlation_threshold = 0.0
        self.seasonality_adjustment = 1.0
        self.volatility_sizing = True

    def calculate_indicators(self, df):
        """Calculate EMA and RSI."""
        if df.empty:
            return df

        # EMA
        df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        return df

    def generate_signal(self, df):
        """Generate Buy/Sell signals."""
        if df.empty or len(df) < self.ema_period:
            return "NEUTRAL"

        last = df.iloc[-1]

        # Long Condition
        if last['close'] > last['ema'] and last['rsi'] > 50:
            return "BUY"

        # Short Condition
        elif last['close'] < last['ema'] and last['rsi'] < 50:
            return "SELL"

        return "NEUTRAL"

    def run(self):
        """Main execution method."""
        logger.info(f"Running MCX Momentum Strategy for {self.symbol}...")

        # In a real scenario, we would fetch live data here.
        # simulating data for demonstration
        dates = pd.date_range(end=datetime.now(), periods=100, freq='15min')
        data = {
            'close': np.random.uniform(50000, 51000, 100)  # Example Gold prices
        }
        df = pd.DataFrame(data, index=dates)

        df = self.calculate_indicators(df)
        signal = self.generate_signal(df)

        logger.info(f"Signal for {self.symbol}: {signal} (Price: {df.iloc[-1]['close']:.2f}, RSI: {df.iloc[-1]['rsi']:.2f})")

        # Here we would place orders via API

if __name__ == "__main__":
    strategy = MCXMomentumStrategy(symbol="GOLD", timeframe="15minute")
    strategy.run()
