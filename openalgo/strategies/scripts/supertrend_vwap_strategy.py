#!/usr/bin/env python3
"""
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis.
Enhanced with Volume Profile and VWAP deviation.
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
logger = logging.getLogger(f"VWAP_{SYMBOL}")

def calculate_vwap(df):
    v = df['volume'].values
    tp = (df['high'] + df['low'] + df['close']) / 3
    df = df.assign(vwap=(tp * v).cumsum() / v.cumsum())

    # Calculate Deviation
    df['vwap_dev'] = (df['close'] - df['vwap']) / df['vwap']
    return df

def analyze_volume_profile(df, n_bins=20):
    """
    Basic Volume Profile analysis.
    Identify Point of Control (POC) - price level with highest volume.
    """
    price_min = df['low'].min()
    price_max = df['high'].max()

    # Create bins
    bins = np.linspace(price_min, price_max, n_bins)

    # Bucket volume into price bins
    # Using 'close' as proxy for trade price in the bin
    df['bin'] = pd.cut(df['close'], bins=bins, labels=False)

    volume_profile = df.groupby('bin')['volume'].sum()

    # Find POC Bin
    if volume_profile.empty:
        return 0, 0

    poc_bin = volume_profile.idxmax()
    poc_volume = volume_profile.max()

    # Approximate POC Price (midpoint of bin)
    if np.isnan(poc_bin):
        return 0, 0

    poc_price = bins[int(poc_bin)] + (bins[1] - bins[0]) / 2

    return poc_price, poc_volume

def run_strategy():
    if not api:
        logger.error("OpenAlgo API not available")
        return

    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting SuperTrend VWAP for {SYMBOL}")

    while True:
        try:
            # Fetch sufficient history for Volume Profile
            df = client.history(symbol=SYMBOL, exchange="NSE", interval="5m",
                                start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))
            if df.empty:
                time.sleep(10)
                continue

            df = calculate_vwap(df)
            last = df.iloc[-1]

            # Volume Profile Analysis
            poc_price, poc_vol = analyze_volume_profile(df)

            # Logic:
            # 1. Price crosses above VWAP
            # 2. Volume Spike (> 1.5x Avg)
            # 3. Price is above POC (Trading above value area)
            # 4. VWAP Deviation is within reasonable bounds (not overextended)

            is_above_vwap = last['close'] > last['vwap']
            is_volume_spike = last['volume'] > df['volume'].mean() * 1.5
            is_above_poc = last['close'] > poc_price
            is_not_overextended = abs(last['vwap_dev']) < 0.02 # Within 2% of VWAP

            if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended:
                logger.info(f"VWAP Crossover Buy for {SYMBOL} | POC: {poc_price:.2f} | Dev: {last['vwap_dev']:.4f}")

                qty = 10
                client.placesmartorder(strategy="SuperTrend VWAP", symbol=SYMBOL, action="BUY",
                                       exchange="NSE", price_type="MARKET", product="MIS",
                                       quantity=qty, position_size=qty)

        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(30)

if __name__ == "__main__":
    run_strategy()
