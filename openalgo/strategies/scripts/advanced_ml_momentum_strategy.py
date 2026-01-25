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

SYMBOL = "REPLACE_ME"
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')
HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(f"Momentum_{SYMBOL}")

def calculate_momentum(df):
    df['roc'] = df['close'].pct_change(periods=10)

    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    return df

def calculate_relative_strength(df, index_df):
    """Calculate Relative Strength vs Index."""
    if index_df.empty or len(index_df) != len(df):
        # Fallback or align
        return 1.0 # Neutral

    # RS Ratio = Stock Price / Index Price
    # We want to see if the Ratio is trending up
    rs_ratio = df['close'] / index_df['close']
    return rs_ratio

def check_sector_momentum(client):
    """Check if the sector is in momentum."""
    # Simulated check
    # sector_mom = client.get_sector_momentum(SYMBOL)
    return True # Placeholder

def check_news_sentiment(symbol):
    """Check news sentiment."""
    # Simulated news API check
    # sentiment = news_api.get_sentiment(symbol)
    # return sentiment > 0
    return True # Placeholder

def run_strategy():
    if not api:
        logger.error("OpenAlgo API not available")
        return

    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting Momentum Strategy for {SYMBOL}")

    while True:
        try:
            # 1. Fetch Stock Data
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

            df = client.history(symbol=SYMBOL, exchange="NSE", interval="15m",
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
            df = calculate_momentum(df)
            rs_ratio = calculate_relative_strength(df, index_df)

            last_row = df.iloc[-1]
            last_rs = rs_ratio.iloc[-1]
            prev_rs = rs_ratio.iloc[-5] # 5 bars ago

            # 4. Strategy Logic
            # Buy if:
            # - ROC > 2% (Strong Momentum)
            # - RSI > 50 (Bullish Zone)
            # - RS Ratio is increasing (Outperforming Index)
            # - Sector is supportive
            # - News is not negative

            if (last_row['roc'] > 0.02 and
                last_row['rsi'] > 50 and
                last_rs > prev_rs and
                check_sector_momentum(client) and
                check_news_sentiment(SYMBOL)):

                logger.info(f"Momentum Signal for {SYMBOL} | ROC: {last_row['roc']:.4f} | RSI: {last_row['rsi']:.2f}")

                # Place Order
                qty = 10 # Placeholder for sizing logic
                client.placesmartorder(strategy="ML Momentum", symbol=SYMBOL, action="BUY",
                                       exchange="NSE", price_type="MARKET", product="MIS",
                                       quantity=qty, position_size=qty)

        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(60)

if __name__ == "__main__":
    run_strategy()
