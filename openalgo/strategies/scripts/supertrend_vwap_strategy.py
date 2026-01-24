#!/usr/bin/env python3
"""
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis.
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(f"VWAP_{SYMBOL}")

def calculate_vwap(df):
    v = df['volume'].values
    tp = (df['high'] + df['low'] + df['close']) / 3
    return df.assign(vwap=(tp * v).cumsum() / v.cumsum())

def run_strategy():
    if not api: return
    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting SuperTrend VWAP for {SYMBOL}")

    while True:
        try:
            df = client.history(symbol=SYMBOL, exchange="NSE", interval="5m",
                                start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))
            if df.empty: continue

            df = calculate_vwap(df)
            last = df.iloc[-1]

            # Logic: Buy if price crosses above VWAP with Volume spike
            if last['close'] > last['vwap'] and last['volume'] > df['volume'].mean() * 1.5:
                logger.info(f"VWAP Crossover Buy for {SYMBOL}")
                # Place Order...

        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(30)

if __name__ == "__main__":
    run_strategy()
