#!/usr/bin/env python3
"""
MCX Commodity Momentum Strategy (Enhanced)
------------------------------------------
Enhanced momentum strategy for MCX commodities (Gold, Silver, Crude Oil, etc.)
incorporating Global Correlation, USD/INR Volatility, and Seasonality.

Strategy Logic:
- Entry Long: Price > EMA(20), RSI > 50, Global Trend != Down, Seasonality > 40
- Entry Short: Price < EMA(20), RSI < 50, Global Trend != Up, Seasonality > 40
- Exit: Target/Stop or Reversal
- Position Sizing: ATR-based, adjusted for USD/INR volatility.
"""

import os
import sys
import pandas as pd
import numpy as np
import logging
from datetime import datetime

# Setup Logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger("MCX_Momentum_Enhanced")

class MCXMomentumStrategy:
    def __init__(self, symbol, timeframe="15minute",
                 global_trend="Neutral", usd_inr_volatility=0.0, seasonality_score=50):
        self.symbol = symbol
        self.timeframe = timeframe

        # External Factors
        self.global_trend = global_trend # 'Up', 'Down', 'Neutral'
        self.usd_inr_volatility = usd_inr_volatility # percentage (e.g. 0.5)
        self.seasonality_score = seasonality_score # 0-100

        # Strategy Parameters
        self.ema_period = 20
        self.rsi_period = 14
        self.atr_period = 14

        # Risk Parameters
        self.stop_loss_atr_mult = 2.0
        self.target_atr_mult = 4.0
        self.base_capital = 100000

    def calculate_indicators(self, df):
        """Calculate EMA, RSI, ATR."""
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

        # ATR
        df['tr'] = np.maximum(df['high'] - df['low'],
                              np.maximum(abs(df['high'] - df['close'].shift(1)),
                                         abs(df['low'] - df['close'].shift(1))))
        df['atr'] = df['tr'].rolling(window=self.atr_period).mean()

        return df

    def calculate_position_size(self, price, atr):
        """
        Calculate position size based on Volatility (ATR) and USD/INR risk.
        Logic: Risk 1% of capital. Stop loss distance = 2 * ATR.
        Size = (Capital * 0.01) / (2 * ATR)
        Adjustment: Reduce size if USD/INR volatility is high (> 0.5%).
        """
        if atr == 0: return 0

        risk_per_trade = self.base_capital * 0.01
        stop_distance = self.stop_loss_atr_mult * atr

        raw_size = risk_per_trade / stop_distance

        # USD/INR Adjustment
        # If volatility > 0.5%, reduce size by 30%
        adjustment_factor = 1.0
        if self.usd_inr_volatility > 0.5:
            adjustment_factor = 0.7
            logger.info(f"High USD/INR Volatility ({self.usd_inr_volatility}%) -> Reducing size by 30%")

        return int(raw_size * adjustment_factor)

    def generate_signal(self, df):
        """Generate Buy/Sell signals with multi-factor filters."""
        if df.empty or len(df) < self.ema_period:
            return "NEUTRAL", 0

        last = df.iloc[-1]
        signal = "NEUTRAL"

        # 1. Technical Signal
        if last['close'] > last['ema'] and last['rsi'] > 50:
            signal = "BUY"
        elif last['close'] < last['ema'] and last['rsi'] < 50:
            signal = "SELL"

        # 2. Seasonality Filter (Skip if score is very low)
        if self.seasonality_score < 40:
             logger.info(f"Signal filtered by Seasonality Score: {self.seasonality_score}")
             return "NEUTRAL", 0

        # 3. Global Trend Filter
        if signal == "BUY" and self.global_trend == "Down":
            logger.info("Signal filtered by Global Trend (Down vs Buy)")
            return "NEUTRAL", 0
        if signal == "SELL" and self.global_trend == "Up":
            logger.info("Signal filtered by Global Trend (Up vs Sell)")
            return "NEUTRAL", 0

        # 4. Position Sizing
        size = 0
        if signal != "NEUTRAL":
            size = self.calculate_position_size(last['close'], last['atr'])

        return signal, size

    def run(self):
        """Main execution method."""
        logger.info(f"Running Enhanced MCX Momentum Strategy for {self.symbol}...")
        logger.info(f"Context: Global={self.global_trend}, USD/INR Vol={self.usd_inr_volatility}%, Seasonality={self.seasonality_score}")

        # Simulating data
        dates = pd.date_range(end=datetime.now(), periods=100, freq='15min')
        base_price = 50000
        volatility = 0.002
        prices = [base_price]
        for _ in range(99):
             prices.append(prices[-1] * (1 + np.random.normal(0, volatility)))

        data = {
            'open': prices,
            'high': [p*1.001 for p in prices],
            'low': [p*0.999 for p in prices],
            'close': prices
        }
        df = pd.DataFrame(data, index=dates)

        df = self.calculate_indicators(df)
        signal, size = self.generate_signal(df)

        logger.info(f"Signal: {signal} | Size: {size} units | Price: {df.iloc[-1]['close']:.2f} | ATR: {df.iloc[-1]['atr']:.2f}")

        # Here we would place orders via API
        return signal, size

if __name__ == "__main__":
    # Test Run
    strategy = MCXMomentumStrategy(symbol="GOLD", global_trend="Up", usd_inr_volatility=0.6, seasonality_score=80)
    strategy.run()
