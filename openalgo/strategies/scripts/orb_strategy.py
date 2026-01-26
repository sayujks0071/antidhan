#!/usr/bin/env python3
"""
ORB Strategy
Opening Range Breakout with pre-market gap analysis and volume confirmation.
Range: First 15 Minutes. Trading Window: Until 10:30 AM.
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
    try:
        # In a real scenario, use history for previous day
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d") # Go back enough to find a trading day
        df = client.history(symbol=SYMBOL, exchange="NSE", interval="day", start_date=start_date, end_date=end_date)
        if not df.empty:
            return df.iloc[-1]['close']
    except Exception as e:
        logger.error(f"Error fetching prev close: {e}")
    return 1000.0 # Fallback

def analyze_gap(open_price, prev_close):
    """Analyze the opening gap."""
    if prev_close == 0: return "Unknown", 0.0

    gap_percent = (open_price - prev_close) / prev_close * 100
    gap_type = "Neutral"
    if gap_percent > 1.0:
        gap_type = "Gap Up"
    elif gap_percent < -1.0:
        gap_type = "Gap Down"
    elif gap_percent > 0.5:
         gap_type = "Mild Gap Up"
    elif gap_percent < -0.5:
         gap_type = "Mild Gap Down"

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
            trading_end = now.replace(hour=10, minute=30, second=0, microsecond=0)
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

                    if not df.empty and len(df) >= 15:
                        # Assuming data starts at 9:15
                        orb_data = df.iloc[:15] # First 15 mins
                        orb_high = orb_data['high'].max()
                        orb_low = orb_data['low'].min()
                        orb_volume_avg = orb_data['volume'].mean()

                        open_price = df.iloc[0]['open']
                        gap_type, gap_pct = analyze_gap(open_price, prev_close)

                        logger.info(f"ORB Calculated: High {orb_high}, Low {orb_low}, Vol Avg {orb_volume_avg:.0f}")
                        logger.info(f"Gap Analysis: {gap_type} ({gap_pct:.2f}%)")

                        orb_period_complete = True
                else:
                    # Still in ORB period
                    time.sleep(30)
                    continue

            # Trading Logic (Post ORB, until 10:30)
            if orb_period_complete and position == 0 and now < trading_end:
                # Fetch live data
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

            elif now > trading_end and position == 0:
                 logger.info("Trading window closed for ORB entries.")
                 break

        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(10)

if __name__ == "__main__":
    run_strategy()
