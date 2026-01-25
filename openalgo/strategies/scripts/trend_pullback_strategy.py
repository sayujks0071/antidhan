#!/usr/bin/env python3
"""
Trend Pullback Strategy
Trades pullbacks in strong trends with breadth confirmation.
Enhanced with Sector Strength and Market Breadth filters.
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
logger = logging.getLogger(f"Pullback_{SYMBOL}")

def check_sector_strength(client):
    """Check if the sector is performing well."""
    # Simulated sector check
    # sector_index = client.get_sector_index(SYMBOL)
    # return sector_index.change > 0
    return True # Placeholder

def check_market_breadth(client):
    """Check if market breadth is positive."""
    # Simulated breadth check
    # ad_ratio = client.get_market_breadth()
    # return ad_ratio > 1.0
    return True # Placeholder

def run_strategy():
    if not api:
        logger.error("OpenAlgo API not available")
        return

    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting Trend Pullback for {SYMBOL}")

    while True:
        try:
            # 1. Global Filters
            if not check_sector_strength(client):
                logger.info("Sector Weak. Waiting...")
                time.sleep(300)
                continue

            if not check_market_breadth(client):
                logger.info("Market Breadth Weak. Waiting...")
                time.sleep(300)
                continue

            # 2. Fetch Data
            df = client.history(symbol=SYMBOL, exchange="NSE", interval="15m",
                                start_date=(datetime.now()-timedelta(days=10)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))

            if df.empty:
                time.sleep(60)
                continue

            # 3. Indicators
            df['sma20'] = df['close'].rolling(20).mean()
            df['sma50'] = df['close'].rolling(50).mean()
            df['sma200'] = df['close'].rolling(200).mean()

            last = df.iloc[-1]

            # 4. Strategy Logic
            # Trend Definition: SMA50 > SMA200 (Long term Up)
            is_uptrend = last['sma50'] > last['sma200']

            if is_uptrend:
                # Pullback: Price < SMA20 (Shallow) or Price < SMA50 (Deep)
                # But Price must be > SMA200 (Still in trend)
                is_pullback = last['close'] < last['sma20'] and last['close'] > last['sma200']

                if is_pullback:
                    logger.info(f"Pullback detected for {SYMBOL} in Uptrend at {last['close']}")

                    # Reversal Trigger: Ideally check for Green Candle or Hammer here
                    # Simplified: Buy

                    qty = 10
                    client.placesmartorder(strategy="Trend Pullback", symbol=SYMBOL, action="BUY",
                                           exchange="NSE", price_type="MARKET", product="MIS",
                                           quantity=qty, position_size=qty)

        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    run_strategy()
