#!/usr/bin/env python3
"""
Sector Momentum Strategy
Trades stocks in strongest sectors.
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
SECTOR_INDEX = "NIFTY BANK" # Example default, should be replaced dynamically
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')
HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(f"SectorMom_{SYMBOL}")

def run_strategy():
    if not api: return
    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting Sector Momentum for {SYMBOL} (Sector: {SECTOR_INDEX})")

    while True:
        try:
            # Fetch Stock and Sector Data
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")

            stock_df = client.history(symbol=SYMBOL, exchange="NSE", interval="1h", start_date=start_date, end_date=end_date)
            # In a real scenario, we'd fetch the Sector Index data too.
            # For now, we assume the Master Strategy filtered for Strong Sectors,
            # so we just check if Stock is outperforming the market/sector logic or just strong trend.

            # Let's simulate sector relative strength check if we can't fetch sector index easily
            # Just check basic momentum

            if stock_df.empty:
                time.sleep(60)
                continue

            # Calculate RS vs Index (Simulated by checking simple ROC)
            stock_roc = (stock_df.iloc[-1]['close'] - stock_df.iloc[0]['close']) / stock_df.iloc[0]['close']

            # Assuming Sector ROC is needed.
            # We will use a placeholder check: Stock ROC > 2% over 10 days

            df = stock_df
            df['sma20'] = df['close'].rolling(20).mean()

            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))

            last = df.iloc[-1]

            # Strong Sector Logic:
            # 1. Stock is above SMA20 (Short term trend)
            # 2. RSI > 55 (Momentum)
            # 3. RS: Outperforming (simulated by positive ROC)

            if last['close'] > last['sma20'] and last['rsi'] > 55 and stock_roc > 0.02:
                logger.info("Stock confirming Sector Momentum. Strong Trend & Momentum. BUY.")
                # client.placesmartorder(...)

        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    run_strategy()
