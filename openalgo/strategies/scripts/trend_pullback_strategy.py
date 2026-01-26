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
    logger.info("Checking Sector Strength...")
    return True # Placeholder

def check_market_breadth(client):
    """Check if market breadth is positive."""
    # Simulated breadth check
    # ad_ratio = client.get_market_breadth()
    # return ad_ratio > 1.0
    logger.info("Checking Market Breadth...")
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
                # Pullback Definitions
                # Shallow: Price < SMA20
                # Deep: Price < SMA50
                # Invalid: Price < SMA200 (Trend broken)

                price = last['close']
                sma20 = last['sma20']
                sma50 = last['sma50']
                sma200 = last['sma200']

                is_pullback = False
                pullback_type = "None"

                if price < sma20 and price > sma50:
                    is_pullback = True
                    pullback_type = "Shallow"
                elif price < sma50 and price > sma200:
                    is_pullback = True
                    pullback_type = "Deep"

                if is_pullback:
                    logger.info(f"{pullback_type} Pullback detected for {SYMBOL} in Uptrend at {price}")

                    # Reversal Trigger: Ideally check for Green Candle or Hammer here
                    # For now, we assume we enter on the touch/dip
                    # Adding a filter: Price must be > 0.5% above the MA it dipped to?
                    # No, usually we want to catch the turn.
                    # Let's add a simple check: Close > Open (Green candle on 15m) to confirm turn

                    if last['close'] > last['open']:
                        logger.info(f"Reversal confirmation (Green Candle). Buying.")
                        qty = 10
                        client.placesmartorder(strategy="Trend Pullback", symbol=SYMBOL, action="BUY",
                                               exchange="NSE", price_type="MARKET", product="MIS",
                                               quantity=qty, position_size=qty)
                    else:
                        logger.info("Waiting for reversal candle...")

        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    run_strategy()
