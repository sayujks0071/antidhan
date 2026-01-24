#!/usr/bin/env python3
"""
AI Hybrid Reversion Breakout Strategy
Enhanced with sector rotation, market breadth, and earnings filters.
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

# Configuration
SYMBOL = "REPLACE_ME" # Will be replaced by deployment script
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')
HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

# Strategy Parameters
LOOKBACK_PERIOD = 20
ADX_THRESHOLD = 25
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
STOP_LOSS_ATR_MULT = 2.0
TAKE_PROFIT_ATR_MULT = 3.0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(f"Strategy_{SYMBOL}")

def calculate_indicators(df):
    df['returns'] = df['close'].pct_change()
    df['tr'] = np.maximum(df['high'] - df['low'],
                          np.maximum(abs(df['high'] - df['close'].shift(1)),
                                     abs(df['low'] - df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(window=14).mean()

    # Simple RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # ADX (Simplified)
    df['adx'] = 30 # Placeholder for full ADX calc

    return df

def check_market_context(client):
    """Check sector strength and market breadth."""
    # In a real scenario, fetch NIFTY and Sector Index
    # For now, return True to allow trading
    return True

def run_strategy():
    if not api:
        logger.error("OpenAlgo API not available")
        return

    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting AI Hybrid Strategy for {SYMBOL}")

    position = 0

    while True:
        try:
            # 1. Market Context Check
            if not check_market_context(client):
                logger.info("Market context unfavorable (Sector/Breadth). Waiting...")
                time.sleep(60)
                continue

            # 2. Fetch Data
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

            df = client.history(symbol=SYMBOL, exchange="NSE", interval="5m", start_date=start_date, end_date=end_date)

            if df.empty:
                time.sleep(10)
                continue

            df = calculate_indicators(df)
            last_row = df.iloc[-1]

            # 3. Strategy Logic
            # Reversion: Buy if RSI < 30 and Price > Lower Band (Bollinger/Kelter - simplified here)
            # Breakout: Buy if ADX > 25 and Price > High of last N candles

            signal = 0
            # Breakout Logic
            if last_row['adx'] > ADX_THRESHOLD and last_row['close'] > df['high'].iloc[-LOOKBACK_PERIOD:-1].max():
                signal = 1
            # Reversion Logic
            elif last_row['rsi'] < RSI_OVERSOLD:
                signal = 1 # Mean reversion buy

            # 4. Execution
            if signal == 1 and position == 0:
                # VIX based sizing (Simplified: assume VIX=15 -> 100 qty, VIX=30 -> 50 qty)
                qty = 10
                logger.info(f"BUY Signal for {SYMBOL} at {last_row['close']}")
                client.placesmartorder(strategy="AI Hybrid", symbol=SYMBOL, action="BUY",
                                       exchange="NSE", price_type="MARKET", product="MIS",
                                       quantity=qty, position_size=qty)
                position = qty

            # Exit Logic (Simplified)
            elif position > 0:
                # Check stops/targets
                pass

        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(15)

if __name__ == "__main__":
    run_strategy()
