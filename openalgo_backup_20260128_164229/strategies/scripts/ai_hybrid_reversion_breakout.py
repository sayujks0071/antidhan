#!/usr/bin/env python3
"""
AI Hybrid Reversion Breakout Strategy
Enhanced with Sector Rotation, Market Breadth, Earnings Filter, and VIX Sizing.
"""
import os
import sys
import time
import argparse
import logging
import pandas as pd
import numpy as np
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

class AIHybridStrategy:
    def __init__(self, symbol, api_key, port, rsi_lower=30, rsi_upper=60, stop_pct=1.0, sector='NIFTY 50'):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)
        self.logger = logging.getLogger(f"AIHybrid_{symbol}")
        self.pm = PositionManager(symbol) if PositionManager else None

        self.rsi_lower = rsi_lower
        self.rsi_upper = rsi_upper
        self.stop_pct = stop_pct
        self.sector = sector

    def get_market_context(self):
        # Simulate VIX and Breadth if not available via API
        return {
            'vix': 15.0, # Simulated
            'breadth_ad_ratio': 1.2, # Simulated
            'earnings_near': False # Simulated
        }

    def check_sector_strength(self):
        try:
            # Check if Sector is in uptrend (Price > SMA20)
            df = self.client.history(symbol=self.sector, interval="day",
                                start_date=(datetime.now()-timedelta(days=30)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))
            if not df.empty:
                df['sma20'] = df['close'].rolling(20).mean()
                return df.iloc[-1]['close'] > df.iloc[-1]['sma20']
        except:
            pass
        return True # Default to True to not block if data missing

    def run(self):
        self.logger.info(f"Starting AI Hybrid for {self.symbol} (Sector: {self.sector})")

        while True:
            if not is_market_open():
                time.sleep(60)
                continue

            try:
                context = self.get_market_context()

                # 1. Earnings Filter
                if context['earnings_near']:
                    self.logger.info("Earnings approaching. Skipping trades.")
                    time.sleep(3600)
                    continue

                # 2. VIX Sizing
                size_multiplier = 1.0
                if context['vix'] > 25:
                    size_multiplier = 0.5
                    self.logger.info(f"High VIX ({context['vix']}). Reducing size by 50%.")

                # 3. Market Breadth Filter
                if context['breadth_ad_ratio'] < 0.7:
                     self.logger.info("Weak Market Breadth. Skipping long entries.")
                     time.sleep(300)
                     continue

                # 4. Sector Rotation Filter
                if not self.check_sector_strength():
                    self.logger.info(f"Sector {self.sector} Weak. Skipping.")
                    time.sleep(300)
                    continue

                # Fetch Data
                df = self.client.history(symbol=self.symbol, interval="5m",
                                    start_date=datetime.now().strftime("%Y-%m-%d"),
                                    end_date=datetime.now().strftime("%Y-%m-%d"))

                if df.empty or len(df) < 20:
                    time.sleep(60)
                    continue

                # Indicators
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                df['rsi'] = 100 - (100 / (1 + rs))

                df['sma20'] = df['close'].rolling(20).mean()
                df['std'] = df['close'].rolling(20).std()
                df['upper'] = df['sma20'] + (2 * df['std'])
                df['lower'] = df['sma20'] - (2 * df['std'])

                last = df.iloc[-1]
                current_price = last['close']

                # Manage Position
                if self.pm and self.pm.has_position():
                    pnl = self.pm.get_pnl(current_price)
                    entry = self.pm.entry_price

                    if (self.pm.position > 0 and current_price < entry * (1 - self.stop_pct/100)) or \
                       (self.pm.position < 0 and current_price > entry * (1 + self.stop_pct/100)):
                        self.logger.info(f"Stop Loss Hit. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')

                    elif (self.pm.position > 0 and current_price > last['sma20']):
                        self.logger.info(f"Reversion Target Hit (SMA20). PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL')

                    time.sleep(60)
                    continue

                # Reversion Logic: RSI < 30 and Price < Lower BB (Oversold)
                if last['rsi'] < self.rsi_lower and last['close'] < last['lower']:
                    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                    if last['volume'] > avg_vol:
                        qty = int(100 * size_multiplier)
                        self.logger.info("Oversold Reversion Signal (RSI<30, <LowerBB). BUY.")
                        self.pm.update_position(qty, current_price, 'BUY')

                # Breakout Logic: RSI > 60 and Price > Upper BB
                elif last['rsi'] > self.rsi_upper and last['close'] > last['upper']:
                    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                    if last['volume'] > avg_vol * 1.5:
                         qty = int(100 * size_multiplier)
                         self.logger.info("Breakout Signal (RSI>60, >UpperBB). BUY.")
                         self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}")
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description='AI Hybrid Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, default='demo_key', help='API Key')
    parser.add_argument('--rsi_lower', type=float, default=30.0, help='RSI Lower Threshold')
    parser.add_argument('--sector', type=str, default='NIFTY 50', help='Sector Benchmark')

    args = parser.parse_args()

    strategy = AIHybridStrategy(args.symbol, args.api_key, args.port, rsi_lower=args.rsi_lower, sector=args.sector)
    strategy.run()

if __name__ == "__main__":
    run_strategy()
