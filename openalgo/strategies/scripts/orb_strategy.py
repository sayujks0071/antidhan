#!/usr/bin/env python3
"""
ORB Strategy (Opening Range Breakout)
Enhanced with Pre-Market Gap Analysis and Volume Confirmation.
"""
import os
import sys
import time
import logging
import argparse
import pandas as pd
from datetime import datetime, timedelta

# Add repo root to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.trading_utils import is_market_open, PositionManager, APIClient
except ImportError:
    try:
        from strategies.utils.trading_utils import is_market_open, PositionManager, APIClient
    except ImportError:
        print("Error: Could not import trading_utils.")
        sys.exit(1)

# Try native import, fallback to our APIClient
try:
    from openalgo import api
except ImportError:
    api = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class ORBStrategy:
    def __init__(self, symbol, quantity, api_key=None, host=None):
        self.symbol = symbol
        self.quantity = quantity
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY')
        if not self.api_key:
             raise ValueError("API Key must be provided via --api_key or OPENALGO_APIKEY env var")

        self.host = host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

        self.logger = logging.getLogger(f"ORB_{symbol}")

        # Initialize API Client
        if api:
            self.client = api(api_key=self.api_key, host=self.host)
            self.logger.info("Using Native OpenAlgo API")
        else:
            self.client = APIClient(api_key=self.api_key, host=self.host)
            self.logger.info("Using Fallback API Client (httpx)")

        self.pm = PositionManager(symbol)

        # Strategy State
        self.orb_high = 0
        self.orb_low = 0
        self.orb_set = False
        self.prev_close = 0
        self.orb_vol_avg = 0

    def get_previous_close(self):
        try:
            end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            df = self.client.history(symbol=self.symbol, exchange="NSE", interval="day", start_date=start_date, end_date=end_date)
            if not df.empty and isinstance(df, pd.DataFrame):
                return df.iloc[-1]['close']
        except Exception as e:
            self.logger.error(f"Error fetching previous close: {e}")
        return 0

    def analyze_gap(self, open_price):
        if self.prev_close == 0: return "Unknown", 0
        gap = (open_price - self.prev_close) / self.prev_close * 100
        return ("Up" if gap > 0 else "Down"), gap

    def run(self):
        self.logger.info(f"Starting ORB Strategy for {self.symbol} | Qty: {self.quantity}")

        self.prev_close = self.get_previous_close()
        self.logger.info(f"Previous Close: {self.prev_close}")

        while True:
            try:
                # Market Hour Check
                if not is_market_open():
                    self.logger.info("Market is closed. Waiting...")
                    time.sleep(60)
                    continue

                now = datetime.now()
                # Times
                market_open = now.replace(hour=9, minute=15, second=0)
                orb_end = now.replace(hour=9, minute=30, second=0)

                # Wait for market open
                if now < market_open:
                    time.sleep(30)
                    continue

                # ORB Calculation Phase (9:15 - 9:30)
                if now < orb_end:
                    time.sleep(30)
                    continue

                # Set ORB if not set
                if not self.orb_set:
                    today = now.strftime("%Y-%m-%d")
                    # Fetch first 15 mins data
                    df = self.client.history(symbol=self.symbol, exchange="NSE", interval="1m", start_date=today, end_date=today)

                    if not df.empty and isinstance(df, pd.DataFrame):
                         # Assuming data starts at 9:15, take first 15 candles
                         orb_df = df.iloc[:15]

                         if len(orb_df) >= 10: # Ensure enough data
                             self.orb_high = orb_df['high'].max()
                             self.orb_low = orb_df['low'].min()
                             self.orb_vol_avg = orb_df['volume'].mean()

                             open_price = df.iloc[0]['open']
                             gap_dir, gap_val = self.analyze_gap(open_price)

                             self.logger.info(f"ORB Set: High {self.orb_high}, Low {self.orb_low}. Gap: {gap_val:.2f}% ({gap_dir}) | Avg Vol: {self.orb_vol_avg}")
                             self.orb_set = True
                         else:
                             self.logger.warning("Not enough data for ORB yet.")

                    if not self.orb_set:
                        time.sleep(60)
                        continue

                # Trading Phase
                if self.orb_set and not self.pm.has_position():
                     # Fetch latest candle
                     df = self.client.history(symbol=self.symbol, exchange="NSE", interval="1m", start_date=now.strftime("%Y-%m-%d"), end_date=now.strftime("%Y-%m-%d"))

                     if not df.empty and isinstance(df, pd.DataFrame):
                         last = df.iloc[-1]

                         # Breakout Up
                         if last['close'] > self.orb_high:
                             # Volume Confirm
                             if last['volume'] > self.orb_vol_avg:
                                 self.logger.info(f"ORB Breakout UP with Volume. BUY at {last['close']}.")

                                 resp = self.client.placesmartorder(strategy="ORB", symbol=self.symbol, action="BUY",
                                                    exchange="NSE", price_type="MARKET", product="MIS",
                                                    quantity=self.quantity, position_size=self.quantity)

                                 if resp:
                                     self.pm.update_position(self.quantity, last['close'], 'BUY')

                         # Breakout Down
                         elif last['close'] < self.orb_low:
                             if last['volume'] > self.orb_vol_avg:
                                 self.logger.info(f"ORB Breakout DOWN with Volume. SELL at {last['close']}.")

                                 resp = self.client.placesmartorder(strategy="ORB", symbol=self.symbol, action="SELL",
                                                    exchange="NSE", price_type="MARKET", product="MIS",
                                                    quantity=self.quantity, position_size=self.quantity)

                                 if resp:
                                      self.pm.update_position(self.quantity, last['close'], 'SELL')

            except KeyboardInterrupt:
                self.logger.info("Stopping strategy...")
                break
            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(10)

def run_strategy(args):
    strategy = ORBStrategy(
        symbol=args.symbol,
        quantity=args.quantity,
        api_key=args.api_key,
        host=args.host
    )
    strategy.run()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ORB Strategy")
    parser.add_argument("--symbol", type=str, required=True, help="Trading Symbol (e.g., RELIANCE)")
    parser.add_argument("--quantity", type=int, default=10, help="Order Quantity")
    parser.add_argument("--api_key", type=str, help="OpenAlgo API Key")
    parser.add_argument("--host", type=str, help="OpenAlgo Server Host")
    parser.add_argument("--port", type=int, default=5001, help="OpenAlgo Server Port (default: 5001)")

    args = parser.parse_args()

    if not args.host:
        args.host = f"http://127.0.0.1:{args.port}"

    run_strategy(args)
