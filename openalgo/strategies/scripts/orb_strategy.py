#!/usr/bin/env python3
"""
ORB Strategy (Opening Range Breakout)
Enhanced with Pre-Market Gap Analysis and Volume Confirmation.
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
    try:
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        df = client.history(symbol=SYMBOL, exchange="NSE", interval="day", start_date=start_date, end_date=end_date)
        if not df.empty:
            return df.iloc[-1]['close']
    except:
        pass
    return 0

def analyze_gap(open_price, prev_close):
    if prev_close == 0: return "Unknown", 0
    gap = (open_price - prev_close) / prev_close * 100
    return ("Up" if gap > 0 else "Down"), gap

def run_strategy():
    if not api: return
    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting ORB for {SYMBOL}")

    orb_high = 0
    orb_low = 0
    orb_set = False

    prev_close = get_previous_close(client)

    while True:
        try:
            now = datetime.now()

            # Times
            market_open = now.replace(hour=9, minute=15, second=0)
            orb_end = now.replace(hour=9, minute=30, second=0)

            if now < market_open:
                time.sleep(30)
                continue

            # ORB Calculation Phase (9:15 - 9:30)
            if now < orb_end:
                # Just waiting or tracking live
                time.sleep(30)
                continue

            # Set ORB if not set
            if not orb_set:
                today = now.strftime("%Y-%m-%d")
                df = client.history(symbol=SYMBOL, exchange="NSE", interval="1m", start_date=today, end_date=today)
                if not df.empty:
                     # Filter for 9:15 to 9:30
                     # Assuming df is indexed by time or we slice first 15 rows
                     orb_df = df.iloc[:15]
                     orb_high = orb_df['high'].max()
                     orb_low = orb_df['low'].min()
                     orb_vol_avg = orb_df['volume'].mean()

                     open_price = df.iloc[0]['open']
                     gap_dir, gap_val = analyze_gap(open_price, prev_close)

                     logger.info(f"ORB Set: High {orb_high}, Low {orb_low}. Gap: {gap_val:.2f}%")
                     orb_set = True

            # Trading Phase
            if orb_set:
                 # Fetch latest candle
                 df = client.history(symbol=SYMBOL, exchange="NSE", interval="1m", start_date=now.strftime("%Y-%m-%d"), end_date=now.strftime("%Y-%m-%d"))
                 last = df.iloc[-1]

                 # Breakout Up
                 if last['close'] > orb_high:
                     # Volume Confirm
                     if last['volume'] > orb_vol_avg:
                         logger.info("ORB Breakout UP with Volume. BUY.")
                         break # Entry

                 # Breakout Down
                 elif last['close'] < orb_low:
                     if last['volume'] > orb_vol_avg:
                         logger.info("ORB Breakout DOWN with Volume. SELL.")
                         break # Entry

        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(10)

if __name__ == "__main__":
    run_strategy()
