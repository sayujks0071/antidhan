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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
    # Using a proxy for ADX: average absolute percentage change scaled
    df['adx_proxy'] = df['returns'].abs().rolling(14).mean() * 1000

    # Bollinger Bands for reversion
    df['sma20'] = df['close'].rolling(20).mean()
    df['std20'] = df['close'].rolling(20).std()
    df['lower_band'] = df['sma20'] - (2 * df['std20'])

    return df

def check_sector_rotation(client):
    """Check if the stock belongs to a leading sector."""
    # In a real implementation, we would map SYMBOL to its sector and check if that sector index is trending up.
    # Simulating sector strength.
    # sector_strength = client.get_technical_indicator(symbol="NIFTY IT", indicator="RSI") ...
    return True # Placeholder: assume strong sector

def check_market_breadth(client):
    """Check overall market breadth (A/D ratio)."""
    # Simulated check
    # breadth = client.get_market_breadth() ...
    return True # Placeholder: assume healthy breadth

def check_earnings(symbol):
    """Check if earnings are upcoming."""
    # In reality, check an earnings calendar API/file
    # Avoid if earnings in +/- 2 days
    return True # Placeholder: assume no earnings

def check_volume_confirmation(df):
    """Check if volume is supportive (delivery volume proxy)."""
    last_vol = df['volume'].iloc[-1]
    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
    return last_vol > avg_vol * 0.8 # Allow slightly below average, but not too low

def get_vix(client):
    """Fetch India VIX."""
    # vix = client.get_quote('INDIA VIX')['ltp']
    return 15.0 # Placeholder

def calculate_position_size(capital, price, atr, vix):
    """Calculate position size based on Volatility (ATR) and VIX."""
    risk_per_trade = capital * 0.01 # 1% risk
    stop_loss_dist = atr * STOP_LOSS_ATR_MULT

    if stop_loss_dist == 0:
        return 0

    qty = int(risk_per_trade / stop_loss_dist)

    # VIX Adjustment
    if vix > 20:
        qty = int(qty * 0.5) # Reduce size by 50% if VIX is high

    return qty

def run_strategy():
    if not api:
        logger.error("OpenAlgo API not available")
        return

    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting AI Hybrid Strategy for {SYMBOL}")

    position = 0
    capital = 100000 # Example capital

    while True:
        try:
            # 1. Market Context Checks
            if not check_sector_rotation(client):
                logger.info("Sector Weakness. Waiting...")
                time.sleep(60)
                continue

            if not check_market_breadth(client):
                logger.info("Market Breadth Weak. Waiting...")
                time.sleep(60)
                continue

            if not check_earnings(SYMBOL):
                logger.info("Earnings approaching. Skipping...")
                time.sleep(3600)
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

            if not check_volume_confirmation(df):
                logger.info("Low Volume. Skipping signal check.")
                time.sleep(60)
                continue

            # 3. Strategy Logic
            signal = 0

            # Breakout Logic: Strong Trend (ADX > 25) + Price Breakout
            # Using adx_proxy as placeholder for ADX
            breakout_level = df['high'].iloc[-LOOKBACK_PERIOD:-1].max()
            if last_row['adx_proxy'] > ADX_THRESHOLD and last_row['close'] > breakout_level:
                signal = 1
                logger.info("Breakout Signal Detected")

            # Reversion Logic: RSI < 30 + Price < Lower Band
            elif last_row['rsi'] < RSI_OVERSOLD and last_row['close'] < last_row['lower_band']:
                signal = 1
                logger.info("Reversion Signal Detected")

            # 4. Execution
            if signal == 1 and position == 0:
                vix = get_vix(client)
                qty = calculate_position_size(capital, last_row['close'], last_row['atr'], vix)

                if qty > 0:
                    logger.info(f"BUY Signal for {SYMBOL} at {last_row['close']} | Qty: {qty} | VIX: {vix}")
                    client.placesmartorder(strategy="AI Hybrid", symbol=SYMBOL, action="BUY",
                                           exchange="NSE", price_type="MARKET", product="MIS",
                                           quantity=qty, position_size=qty)
                    position = qty
                else:
                    logger.warning("Calculated quantity is 0. Check risk parameters.")

            # Exit Logic (Simplified)
            elif position > 0:
                # In a real loop, we would track the PnL and exit based on SL/TP
                # Here we simulate an exit after some condition or use order updates
                pass

        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(15)

if __name__ == "__main__":
    run_strategy()
