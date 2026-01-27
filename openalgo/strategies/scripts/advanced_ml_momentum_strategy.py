#!/usr/bin/env python3
"""
Advanced ML Momentum Strategy
Momentum with relative strength and sector overlay.
Enhanced with RS vs NIFTY, sector momentum, and news sentiment.
"""
import os
import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

try:
    from openalgo import api
except ImportError:
    api = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class AdvancedMLMomentumStrategy:
    def __init__(self):
        self.symbol = "REPLACE_ME"
        self.api_key = os.getenv('OPENALGO_APIKEY', 'demo_key')
        self.host = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

        # Optimization Parameters
        self.threshold = 55   # RSI Threshold
        self.stop_pct = 2.5   # Stop Loss %

        self.logger = logging.getLogger(f"Momentum_{self.symbol}")

        if api:
            self.client = api(api_key=self.api_key, host=self.host)
        else:
            self.logger.error("OpenAlgo API not available")
            self.client = None

    def calculate_momentum(self, df):
        df['roc'] = df['close'].pct_change(periods=10)

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        return df

    def calculate_relative_strength(self, df, index_df):
        """Calculate Relative Strength vs Index."""
        if index_df.empty or len(index_df) != len(df):
            # Fallback or align
            return pd.Series([1.0]*len(df), index=df.index) # Neutral

        # RS Ratio = Stock Price / Index Price
        # We want to see if the Ratio is trending up
        rs_ratio = df['close'] / index_df['close']
        return rs_ratio

    def check_sector_momentum(self):
        """Check if the sector is in momentum."""
        # Simulated check
        # sector_mom = client.get_sector_momentum(SYMBOL)
        return True # Placeholder

    def check_news_sentiment(self):
        """Check news sentiment."""
        # Simulated news API check
        # sentiment = news_api.get_sentiment(symbol)
        # return sentiment > 0
        return True # Placeholder

    def run(self):
        if not self.client:
            return

        self.logger.info(f"Starting Momentum Strategy for {self.symbol} | RSI Thr: {self.threshold} | Stop: {self.stop_pct}")

        while True:
            try:
                # 1. Fetch Stock Data
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

                df = self.client.history(symbol=self.symbol, exchange="NSE", interval="15m",
                                    start_date=start_date, end_date=end_date)
                if df.empty:
                    time.sleep(10)
                    continue

                # 2. Fetch Index Data (Simulated or Real)
                # index_df = client.history(symbol="NIFTY 50", ...)
                # Simulating index data matching stock df length
                index_data = {
                    'close': np.random.uniform(10000, 11000, len(df))
                }
                index_df = pd.DataFrame(index_data, index=df.index)

                # 3. Indicators
                df = self.calculate_momentum(df)
                rs_ratio = self.calculate_relative_strength(df, index_df)

                last_row = df.iloc[-1]
                last_rs = rs_ratio.iloc[-1]
                prev_rs = rs_ratio.iloc[-5] # 5 bars ago

                # 4. Strategy Logic
                # Buy if:
                # - ROC > 2% (Strong Momentum)
                # - RSI > Threshold (Bullish Zone)
                # - RS Ratio is increasing (Outperforming Index)
                # - Sector is supportive
                # - News is not negative

                if (last_row['roc'] > 0.02 and
                    last_row['rsi'] > self.threshold and
                    last_rs > prev_rs and
                    self.check_sector_momentum() and
                    self.check_news_sentiment()):

                    self.logger.info(f"Momentum Signal for {self.symbol} | ROC: {last_row['roc']:.4f} | RSI: {last_row['rsi']:.2f}")

                    # Place Order
                    qty = 10 # Placeholder for sizing logic
                    self.client.placesmartorder(strategy="ML Momentum", symbol=self.symbol, action="BUY",
                                        exchange="NSE", price_type="MARKET", product="MIS",
                                        quantity=qty, position_size=qty)

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(60)

def run_strategy():
    strategy = AdvancedMLMomentumStrategy()
    strategy.run()

if __name__ == "__main__":
    run_strategy()
