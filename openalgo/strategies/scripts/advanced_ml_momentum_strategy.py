#!/usr/bin/env python3
"""
Advanced ML Momentum Strategy
Momentum with relative strength and sector overlay.
Refactored to remove mocks and use real API client.
"""
import os
import sys
import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[3]))

try:
    from openalgo.strategies.utils.trading_utils import APIClient
except ImportError:
    # Fallback if running from a different context
    logging.warning("Could not import APIClient from utils, using local definition or failing.")
    from openalgo import api as APIClient # Attempt to fallback to core api if available

SYMBOL = os.getenv("STRATEGY_SYMBOL", "RELIANCE")
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
    if index_df.empty:
        return pd.Series(1.0, index=df.index)

    # Align dataframes
    common_index = df.index.intersection(index_df.index)
    if common_index.empty:
        return pd.Series(1.0, index=df.index)

    df_aligned = df.loc[common_index]
    index_aligned = index_df.loc[common_index]

    # RS Ratio = Stock Price / Index Price
    rs_ratio = df_aligned['close'] / index_aligned['close']
    return rs_ratio

def check_sector_momentum(df):
    """
    Check if the asset is in a long term uptrend (Simple proxy for sector momentum).
    Returns True if Close > SMA(50)
    """
    if len(df) < 200:
        return True

    sma200 = df['close'].rolling(window=200).mean().iloc[-1]
    return df['close'].iloc[-1] > sma200

def run_strategy():
    client = APIClient(api_key=API_KEY, host=HOST)
    logger.info(f"Starting Momentum Strategy for {SYMBOL}")

    while True:
        try:
            # 1. Fetch Stock Data
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

            df = client.history(symbol=SYMBOL, exchange="NSE", interval="15m",
                                start_date=start_date, end_date=end_date)

            if df.empty:
                logger.warning(f"No data for {SYMBOL}, retrying...")
                time.sleep(10)
                continue

            # Ensure datetime index
            if 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
                df.set_index('datetime', inplace=True)

            # 2. Fetch Index Data (Real NIFTY 50)
            index_df = client.history(symbol="NIFTY 50", exchange="NSE_INDEX", interval="15m",
                                      start_date=start_date, end_date=end_date)
            if not index_df.empty and 'datetime' in index_df.columns:
                 index_df['datetime'] = pd.to_datetime(index_df['datetime'])
                 index_df.set_index('datetime', inplace=True)

            # 3. Indicators
            df = calculate_momentum(df)
            rs_ratio = calculate_relative_strength(df, index_df)

            last_row = df.iloc[-1]
            last_rs = rs_ratio.iloc[-1] if not rs_ratio.empty else 1.0
            prev_rs = rs_ratio.iloc[-5] if len(rs_ratio) > 5 else 1.0

            # 4. Strategy Logic
            # Buy if:
            # - ROC > 1% (Positive Momentum)
            # - RSI > 55 (Bullish Zone)
            # - RS Ratio is increasing (Outperforming Index)
            # - Sector/Trend is supportive (Price > SMA50)

            if (last_row.get('roc', 0) > 0.01 and
                last_row.get('rsi', 0) > 55 and
                last_rs > prev_rs and
                check_sector_momentum(df)):

                logger.info(f"Momentum Signal for {SYMBOL} | ROC: {last_row.get('roc'):.4f} | RSI: {last_row.get('rsi'):.2f}")

                # Place Order
                qty = int(os.getenv("STRATEGY_QUANTITY", 1))
                client.placesmartorder(strategy="ML Momentum", symbol=SYMBOL, action="BUY",
                                       exchange="NSE", price_type="MARKET", product="MIS",
                                       quantity=qty, position_size=qty)
            else:
                logger.info(f"No signal. ROC: {last_row.get('roc', 0):.4f}, RSI: {last_row.get('rsi', 0):.2f}")

        except KeyboardInterrupt:
            logger.info("Stopping strategy...")
            break
        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(60)

if __name__ == "__main__":
    run_strategy()
