#!/usr/bin/env python3
"""
Sector Momentum Strategy
Trades stocks in strongest sectors.
"""
import os
import sys
import time
import argparse
import logging
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
except ImportError:
    print("Warning: openalgo package not found or imports failed.")
    APIClient = None
    PositionManager = None
    is_market_open = lambda: True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class SectorMomentumStrategy:
    def __init__(self, symbol, api_key, port, sector_index, stop_pct=1.5):
        self.symbol = symbol
        self.sector_index = sector_index
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)
        self.logger = logging.getLogger(f"SectorMom_{symbol}")
        self.pm = PositionManager(symbol) if PositionManager else None
        self.stop_pct = stop_pct

    def run(self):
        self.logger.info(f"Starting Sector Momentum for {self.symbol} (Sector: {self.sector_index})")

        while True:
            if not is_market_open():
                time.sleep(60)
                continue

            try:
                # 1. Check Sector Strength
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")

                # Fetch Sector Index Data
                sector_df = self.client.history(symbol=self.sector_index, interval="day", start_date=start_date, end_date=end_date)

                sector_strong = False
                if not sector_df.empty and len(sector_df) >= 10:
                    sector_df['sma10'] = sector_df['close'].rolling(10).mean()
                    if sector_df.iloc[-1]['close'] > sector_df.iloc[-1]['sma10']:
                        sector_strong = True
                else:
                    # Fallback if sector data unavailable: Assume strong if user picked it
                    sector_strong = True

                if not sector_strong:
                    self.logger.info(f"Sector {self.sector_index} is weak. Waiting.")
                    time.sleep(300)
                    continue

                # 2. Check Stock Momentum
                stock_df = self.client.history(symbol=self.symbol, interval="1h", start_date=start_date, end_date=end_date)

                if stock_df.empty or len(stock_df) < 20:
                    time.sleep(60)
                    continue

                # Calculate RS vs Index (Simulated by checking simple ROC if index data matching is hard)
                stock_roc = (stock_df.iloc[-1]['close'] - stock_df.iloc[0]['close']) / stock_df.iloc[0]['close']

                stock_df['sma20'] = stock_df['close'].rolling(20).mean()

                # RSI
                delta = stock_df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                stock_df['rsi'] = 100 - (100 / (1 + rs))

                last = stock_df.iloc[-1]
                current_price = last['close']

                # Manage Position
                if self.pm and self.pm.has_position():
                    pnl = self.pm.get_pnl(current_price)
                    entry = self.pm.entry_price

                    # Stop Loss
                    if (self.pm.position > 0 and current_price < entry * (1 - self.stop_pct/100)):
                        self.logger.info(f"Stop Loss Hit. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL')

                    # Trailing Stop or Exit if RSI drops
                    elif (self.pm.position > 0 and last['rsi'] < 50):
                         self.logger.info(f"Momentum Lost (RSI<50). Exit. PnL: {pnl}")
                         self.pm.update_position(abs(self.pm.position), current_price, 'SELL')

                    time.sleep(60)
                    continue

                # Entry Logic:
                # 1. Sector Strong (Checked)
                # 2. Stock Price > SMA20
                # 3. RSI > 55
                # 4. Stock ROC Positive

                if last['close'] > last['sma20'] and last['rsi'] > 55 and stock_roc > 0:
                    self.logger.info("Stock confirming Sector Momentum. Strong Trend & Momentum. BUY.")
                    self.pm.update_position(100, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}")
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description='Sector Momentum Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--sector_index', type=str, default='NIFTY BANK', help='Sector Index Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, default='demo_key', help='API Key')

    args = parser.parse_args()

    strategy = SectorMomentumStrategy(args.symbol, args.api_key, args.port, sector_index=args.sector_index)
    strategy.run()

if __name__ == "__main__":
    run_strategy()
