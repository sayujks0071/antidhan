#!/usr/bin/env python3
"""
Trend Pullback Strategy
Enhanced with Sector Strength, Pullback Depth, and Market Breadth.
"""
import os
import sys
import time
import argparse
import logging
import pandas as pd
from datetime import datetime, timedelta

# Add repo root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.trading_utils import is_market_open, PositionManager, APIClient
except ImportError:
    print("Warning: openalgo package not found or imports failed.")
    APIClient = None
    PositionManager = None
    is_market_open = lambda: True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class TrendPullbackStrategy:
    def __init__(self, symbol, quantity, api_key=None, host=None, sector='NIFTY 50'):
        self.symbol = symbol
        self.quantity = quantity
        self.sector = sector
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY', 'demo_key')
        self.host = host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

        self.logger = logging.getLogger(f"Pullback_{symbol}")
        self.client = APIClient(api_key=self.api_key, host=self.host)
        self.pm = PositionManager(symbol) if PositionManager else None

    def check_market_breadth(self):
        # In a real system, fetch Advance/Decline ratio
        # Here we can check NIFTY 50 trend as a proxy for breadth health
        try:
            df = self.client.history(symbol="NIFTY 50", interval="day",
                                start_date=(datetime.now()-timedelta(days=2)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))
            if not df.empty and len(df) >= 2:
                return df.iloc[-1]['close'] > df.iloc[-2]['close'] # Simple Green Day Check
        except:
            pass
        return True # Default to True if data missing to avoid blocking

    def check_sector_strength(self):
        try:
            df = self.client.history(symbol=self.sector, interval="day",
                                start_date=(datetime.now()-timedelta(days=20)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))
            if not df.empty:
                df['sma20'] = df['close'].rolling(20).mean()
                return df.iloc[-1]['close'] > df.iloc[-1]['sma20'] # Sector above SMA20
        except:
            pass
        return True

    def run(self):
        self.logger.info(f"Starting Trend Pullback for {self.symbol}")

        while True:
            try:
                if not is_market_open():
                    time.sleep(60)
                    continue

                if not self.check_market_breadth():
                    self.logger.info("Market Breadth weak. Waiting.")
                    time.sleep(300)
                    continue

                if not self.check_sector_strength():
                    self.logger.info("Sector Weak. Waiting.")
                    time.sleep(300)
                    continue

                # Fetch Data
                df = self.client.history(symbol=self.symbol, interval="15m",
                                    start_date=(datetime.now()-timedelta(days=10)).strftime("%Y-%m-%d"),
                                    end_date=datetime.now().strftime("%Y-%m-%d"))

                if df.empty or len(df) < 200:
                    time.sleep(60)
                    continue

                df['sma20'] = df['close'].rolling(20).mean()
                df['sma50'] = df['close'].rolling(50).mean()
                df['sma200'] = df['close'].rolling(200).mean()

                last = df.iloc[-1]
                price = last['close']

                if self.pm and self.pm.has_position():
                    # Exit logic
                    entry = self.pm.entry_price
                    # Target 1:2
                    target = entry * 1.04
                    stop = entry * 0.98

                    if price >= target:
                        self.logger.info("Target Hit.")
                        self.pm.update_position(self.quantity, price, 'SELL')
                    elif price <= stop:
                        self.logger.info("Stop Hit.")
                        self.pm.update_position(self.quantity, price, 'SELL')
                    continue

                # Entry Logic
                # Trend: SMA50 > SMA200 (Uptrend)
                if last['sma50'] > last['sma200']:

                    # Pullback Logic
                    # Shallow: Price dipped below SMA20 but Close > SMA20 (Reclaimed)
                    # Deep: Price dipped below SMA50 but Close > SMA50 (Reclaimed)

                    reclaimed_sma20 = (df.iloc[-2]['close'] < df.iloc[-2]['sma20']) and (last['close'] > last['sma20'])
                    reclaimed_sma50 = (df.iloc[-2]['close'] < df.iloc[-2]['sma50']) and (last['close'] > last['sma50'])

                    if reclaimed_sma20 or reclaimed_sma50:
                        # Reversal Confirmation: Green Candle
                        if last['close'] > last['open']:
                            self.logger.info("Pullback Reversal Confirmed. BUY.")
                            if self.pm: self.pm.update_position(self.quantity, price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}")
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description="Trend Pullback Strategy")
    parser.add_argument("--symbol", type=str, required=True, help="Symbol")
    parser.add_argument("--quantity", type=int, default=10, help="Qty")
    parser.add_argument("--api_key", type=str, default='demo_key', help="API Key")
    parser.add_argument("--host", type=str, default='http://127.0.0.1:5001', help="Host")
    parser.add_argument("--sector", type=str, default="NIFTY 50", help="Sector Benchmark")

    args = parser.parse_args()
    strategy = TrendPullbackStrategy(args.symbol, args.quantity, args.api_key, args.host, sector=args.sector)
    strategy.run()

if __name__ == "__main__":
    run_strategy()
