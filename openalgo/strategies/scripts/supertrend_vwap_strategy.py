#!/usr/bin/env python3
"""
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis.
Enhanced with Volume Profile and VWAP deviation.
Now includes Position Management and Market Hour checks.
"""
import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add repo root to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
except ImportError:
    # Fallback if running from a different context
    try:
        from strategies.utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
    except ImportError:
        pass # Will handle gracefully in main
        api = None

# Try native import, fallback to our APIClient
try:
    from openalgo import api
except ImportError:
    api = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

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

def check_sector_correlation(symbol):
    """Check if the stock is correlated with its sector."""
    # Simulated check
    # sector_index = get_sector(symbol)
    # correlation = calculate_correlation(symbol, sector_index)
    # return correlation > 0.7
    return True # Placeholder

def run_strategy(args):
    symbol = args.symbol
    api_key = args.api_key or os.getenv('OPENALGO_APIKEY', 'demo_key')
    host = args.host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
    quantity = args.quantity

    logger = logging.getLogger(f"VWAP_{symbol}")

    # Initialize API Client
    client = None
    if api:
        client = api(api_key=api_key, host=host)
        logger.info("Using Native OpenAlgo API")
    else:
        # If openalgo is not installed, we can try to use APIClient if available
        if 'APIClient' in globals():
            client = APIClient(api_key=api_key, host=host)
            logger.info("Using Fallback API Client (httpx)")
        else:
             logger.error("No API client available. Install openalgo or ensure utils are accessible.")
             return

    # Initialize Position Manager
    pm = None
    if 'PositionManager' in globals():
        pm = PositionManager(symbol)
    else:
        logger.warning("PositionManager not available. Running without position tracking.")

    logger.info(f"Starting SuperTrend VWAP for {symbol} | Qty: {quantity}")

    while True:
        try:
            # Market Hour Check
            if not args.ignore_time and 'is_market_open' in globals() and not is_market_open():
                logger.info("Market is closed. Waiting...")
                time.sleep(60)
                continue

            if not check_sector_correlation(symbol):
                logger.info("Sector Correlation Low. Waiting...")
                time.sleep(300)
                continue

            # Fetch sufficient history for Volume Profile (last 5 days)
            df = client.history(symbol=symbol, exchange="NSE", interval="5m",
                                start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))

            if df.empty or not isinstance(df, pd.DataFrame):
                logger.warning("No data received. Retrying...")
                time.sleep(10)
                continue

            # Calculate Intraday VWAP (resetting daily)
            if 'calculate_intraday_vwap' in globals():
                df = calculate_intraday_vwap(df)
            else:
                # Basic VWAP fallback
                 df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
                 df['vwap_dev'] = (df['close'] - df['vwap']) / df['vwap']

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

            logger.debug(f"Price: {last['close']} | VWAP: {last['vwap']:.2f} | POC: {poc_price:.2f}")

            if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended:
                if pm and not pm.has_position():
                    logger.info(f"VWAP Crossover Buy for {symbol} | POC: {poc_price:.2f} | Dev: {last['vwap_dev']:.4f}")

                    # Place Order
                    resp = client.placesmartorder(strategy="SuperTrend VWAP", symbol=symbol, action="BUY",
                                           exchange="NSE", price_type="MARKET", product="MIS",
                                           quantity=quantity, position_size=quantity)

                    if resp: # Assuming resp is not None/Empty on success
                        pm.update_position(quantity, last['close'], 'BUY')
                elif not pm:
                     logger.info(f"VWAP Crossover Buy Signal (No PM) for {symbol}")
                else:
                    logger.debug("Signal detected but position already open.")

            # Exit Logic (Simple stop/target or reverse) - For now just log
            # In a real strategy, checking PnL or technical exit conditions goes here.

        except KeyboardInterrupt:
            logger.info("Stopping strategy...")
            break
        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(30)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SuperTrend VWAP Strategy")
    parser.add_argument("--symbol", type=str, required=True, help="Trading Symbol (e.g., RELIANCE)")
    parser.add_argument("--quantity", type=int, default=10, help="Order Quantity")
    parser.add_argument("--api_key", type=str, help="OpenAlgo API Key")
    parser.add_argument("--host", type=str, help="OpenAlgo Server Host")
    parser.add_argument("--ignore_time", action="store_true", help="Ignore market hours check")

    args = parser.parse_args()
    run_strategy(args)
