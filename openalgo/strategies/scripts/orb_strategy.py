#!/usr/bin/env python3
"""
ORB Strategy
Opening Range Breakout with pre-market gap analysis and volume confirmation.
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
logger = logging.getLogger(f"ORB_{SYMBOL}")

def get_previous_close(client):
    """Fetch previous day's close price."""
    # Simulating fetching previous close
    # prev_ohlc = client.get_ohlc(SYMBOL)
    # return prev_ohlc['close']
    return 1000.0 # Placeholder

def analyze_gap(open_price, prev_close):
    """Analyze the opening gap."""
    gap_percent = (open_price - prev_close) / prev_close * 100
    gap_type = "Neutral"
    if gap_percent > 1.0:
        gap_type = "Gap Up"
    elif gap_percent < -1.0:
        gap_type = "Gap Down"

    return gap_type, gap_percent

def run_strategy():
    if not api:
        logger.error("OpenAlgo API not available")
        return

    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting ORB for {SYMBOL}")

    orb_high = None
    orb_low = None
    orb_period_complete = False
    orb_volume_avg = 0
    prev_close = get_previous_close(client)

    # State tracking
    position = 0

    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # Define ORB period (9:15 to 9:30)
            market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            orb_end = now.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

            if now < market_open:
                logger.info("Waiting for market open...")
                time.sleep(60)
                continue

            if now > market_close:
                logger.info("Market Closed.")
                break

            # ORB Calculation Logic
            if not orb_period_complete:
                if now > orb_end:
                    # Calculate ORB
                    df = client.history(symbol=SYMBOL, exchange="NSE", interval="1m",
                                        start_date=today_str, end_date=today_str)

                    if not df.empty:
                        # Assuming 'date' column exists or using index.
                        # Filtering for data strictly between 9:15 and 9:30
                        # For simplicity, we assume the history call returns today's data so far

                        # Verify we have enough data points
                        if len(df) >= 15:
                            orb_data = df.iloc[:15] # First 15 mins
                            orb_high = orb_data['high'].max()
                            orb_low = orb_data['low'].min()
                            orb_volume_avg = orb_data['volume'].mean()

                            open_price = df.iloc[0]['open']
                            gap_type, gap_pct = analyze_gap(open_price, prev_close)

                            logger.info(f"ORB Calculated: High {orb_high}, Low {orb_low}")
                            logger.info(f"Gap Analysis: {gap_type} ({gap_pct:.2f}%)")

                            orb_period_complete = True
                else:
                    time.sleep(30)
                    continue

            # Trading Logic (Post ORB)
            if orb_period_complete and position == 0:
                # Fetch live data (Simulated here via history for consistency)
                df = client.history(symbol=SYMBOL, exchange="NSE", interval="1m",
                                    start_date=today_str, end_date=today_str)

                if not df.empty:
                    last = df.iloc[-1]
                    ltp = last['close']
                    volume = last['volume']

                    # Volume Confirmation: Current volume > ORB Avg Volume
                    volume_confirmed = volume > orb_volume_avg

                    if ltp > orb_high and volume_confirmed:
                        logger.info(f"ORB Breakout UP at {ltp} with Volume")
                        qty = 10
                        client.placesmartorder(strategy="ORB", symbol=SYMBOL, action="BUY",
                                               exchange="NSE", price_type="MARKET", product="MIS",
                                               quantity=qty, position_size=qty)
                        position = qty

                    elif ltp < orb_low and volume_confirmed:
                        logger.info(f"ORB Breakout DOWN at {ltp} with Volume")
                        qty = 10
                        client.placesmartorder(strategy="ORB", symbol=SYMBOL, action="SELL",
                                               exchange="NSE", price_type="MARKET", product="MIS",
                                               quantity=qty, position_size=qty)
                        position = -qty

        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(10)

if __name__ == "__main__":
    run_strategy()
