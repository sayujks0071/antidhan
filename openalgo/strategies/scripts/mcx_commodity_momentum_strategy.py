#!/usr/bin/env python3
"""
MCX Commodity Momentum Strategy (Enhanced)
------------------------------------------
A momentum strategy for MCX commodities with global correlation,
USD/INR adjustment, and seasonality filters.

Usage:
    python3 mcx_commodity_momentum_strategy.py
"""

import os
import sys
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Ensure we can import from openalgo
project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

try:
    from openalgo.strategies.utils.trading_utils import APIClient
except ImportError:
    print("Warning: openalgo.strategies.utils.trading_utils not found. Using local mocks if needed.")
    APIClient = None

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MCX_Momentum_Enhanced")

class MCXMomentumStrategy:
    def __init__(self, symbol="GOLD", timeframe="15minute",
                 usd_inr_factor=1.0, global_correlation_threshold=0.5,
                 seasonality_factor=1.0):

        self.symbol = symbol
        self.timeframe = timeframe
        self.api_key = os.getenv("KITE_API_KEY", "dummy_key")
        self.api = APIClient(self.api_key, host="http://127.0.0.1:5001") if APIClient else None

        # Strategy Parameters
        self.ema_period = 20
        self.rsi_period = 14
        self.stop_loss_pct = 0.01
        self.target_pct = 0.02

        # Enhanced Filters
        self.usd_inr_factor = usd_inr_factor
        self.global_correlation_threshold = global_correlation_threshold
        self.seasonality_factor = seasonality_factor

        # State
        self.position = 0

    def fetch_data(self):
        """Fetch market data via API or simulate."""
        df = pd.DataFrame()
        if self.api:
            try:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=5)
                s_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
                e_str = end_date.strftime('%Y-%m-%d %H:%M:%S')

                df = self.api.history(self.symbol, exchange="MCX", interval=self.timeframe,
                                      start_date=s_str, end_date=e_str)
            except Exception as e:
                logger.warning(f"API fetch failed: {e}")

        if df.empty:
            logger.info("Using simulated data.")
            return self._simulate_data()
        return df

    def _simulate_data(self):
        """Simulate data for testing."""
        dates = pd.date_range(end=datetime.now(), periods=200, freq='15min')
        prices = [50000]
        for _ in range(199):
            prices.append(prices[-1] * (1 + np.random.normal(0, 0.002)))

        data = {
            'close': prices,
            'high': [p * 1.001 for p in prices],
            'low': [p * 0.999 for p in prices],
            'volume': np.random.randint(100, 1000, 200)
        }
        return pd.DataFrame(data, index=dates)

    def calculate_indicators(self, df):
        """Calculate EMA and RSI."""
        df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()

        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        return df

    def check_filters(self, signal):
        """Apply enhanced filters (USD/INR, Seasonality, Correlation)."""
        # 1. USD/INR Filter (Simulated check)
        # If buying Gold/Silver, weak INR (High Factor) is good.
        if self.symbol in ['GOLD', 'SILVER'] and signal == "BUY":
            if self.usd_inr_factor < 0.99: # Strong INR
                logger.info("Signal Rejected: USD/INR indicates headwinds (Strong INR)")
                return False

        # 2. Seasonality
        if self.seasonality_factor < 0.5: # Weak season
            logger.info("Signal Rejected: Weak Seasonality")
            return False

        # 3. Global Correlation (Mock check)
        # In real usage, this would check correlation with global price
        # Here we assume it passes if not explicitly set to fail
        if self.global_correlation_threshold > 0.8:
            # Stricter check
            pass

        return True

    def generate_signal(self, df):
        """Generate Buy/Sell signals with filters."""
        if df.empty or len(df) < 50:
            return "NEUTRAL"

        last = df.iloc[-1]

        signal = "NEUTRAL"
        if last['close'] > last['ema'] and last['rsi'] > 55:
            signal = "BUY"
        elif last['close'] < last['ema'] and last['rsi'] < 45:
            signal = "SELL"

        if signal != "NEUTRAL":
            if self.check_filters(signal):
                return signal
            else:
                return "NEUTRAL"

        return "NEUTRAL"

    def run(self):
        """Execute strategy cycle."""
        logger.info(f"Running MCX Momentum Strategy for {self.symbol}")
        logger.info(f"Filters - USD/INR: {self.usd_inr_factor}, Seasonality: {self.seasonality_factor}")

        df = self.fetch_data()
        df = self.calculate_indicators(df)
        signal = self.generate_signal(df)

        logger.info(f"Final Signal: {signal}")

        if signal in ["BUY", "SELL"]:
            # Position Sizing Logic (Volatility Based)
            atr = df['close'].rolling(14).mean().iloc[-1] * 0.01 # Approx ATR
            risk_per_share = atr * 2
            capital_risk = 10000 # Fixed risk amount
            qty = int(capital_risk / risk_per_share) if risk_per_share > 0 else 1

            logger.info(f"Suggested Entry: {df.iloc[-1]['close']:.2f}, Qty: {qty}")
            # Order placement code would go here using self.api.placesmartorder

if __name__ == "__main__":
    # Example usage with different filter settings
    strategy = MCXMomentumStrategy(symbol="GOLD", usd_inr_factor=1.01, seasonality_factor=0.9)
    strategy.run()
