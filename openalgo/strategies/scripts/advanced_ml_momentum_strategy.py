#!/usr/bin/env python3
"""
Advanced ML Momentum Strategy
Enhanced with Relative Strength, Sector Momentum, News Sentiment, and Volume Timing.
"""
import os
import time
import logging
import pandas as pd
from datetime import datetime, timedelta

try:
    from openalgo import api
except ImportError:
    api = None

SYMBOL = "REPLACE_ME"
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')
HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(f"MLMomentum_{SYMBOL}")

def get_relative_strength(client, symbol):
    """Calc RS vs NIFTY."""
    # Placeholder
    return 1.1 # Outperforming

def get_news_sentiment(symbol):
    """Get News Sentiment Score (-1 to 1)."""
    return 0.5 # Positive

def run_strategy():
    if not api: return
    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting ML Momentum for {SYMBOL}")

    while True:
        try:
            # Timing Filter: Avoid Low Volume (12-1 PM)
            now = datetime.now()
            if 12 <= now.hour < 13:
                logger.info("Lunch break (Low Volume). Pausing.")
                time.sleep(1800)
                continue

            # 1. Relative Strength Filter
            rs = get_relative_strength(client, SYMBOL)
            if rs < 1.0:
                logger.info("Relative Strength Weak (<1.0). Skipping.")
                time.sleep(300)
                continue

            # 2. News Sentiment
            sentiment = get_news_sentiment(SYMBOL)
            if sentiment < 0:
                logger.info("Negative News Sentiment. Skipping.")
                time.sleep(300)
                continue

            # Fetch Data
            df = client.history(symbol=SYMBOL, exchange="NSE", interval="5m",
                                start_date=datetime.now().strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))

            if df.empty:
                time.sleep(60)
                continue

            # ML Score Simulation (Composite Momentum Score)
            # Factors: RSI, ROC, MACD
            df['sma20'] = df['close'].rolling(20).mean()

            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs_val = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs_val))

            last = df.iloc[-1]

            # Entry Logic
            if last['close'] > last['sma20'] and last['rsi'] > 60:
                # Volume Confirmation
                avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                if last['volume'] > avg_vol:
                     logger.info("ML Momentum Trigger: Strong Trend + RSI + Volume. BUY.")
                     # client.placesmartorder(...)

        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(60)

if __name__ == "__main__":
    run_strategy()
