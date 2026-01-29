#!/usr/bin/env python3
"""
Advanced ML Momentum Strategy
Momentum with relative strength and sector overlay.
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

class MLMomentumStrategy:
    def __init__(self, symbol, api_key, port, threshold=0.01, stop_pct=1.0, sector='NIFTY 50'):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)
        self.logger = logging.getLogger(f"MLMomentum_{symbol}")
        self.pm = PositionManager(symbol) if PositionManager else None

        self.roc_threshold = threshold
        self.stop_pct = stop_pct
        self.sector = sector

    def calculate_relative_strength(self, df, index_df):
        if index_df.empty: return 1.0

        # Align timestamps (simplistic approach using last N periods)
        try:
            stock_roc = df['close'].pct_change(10).iloc[-1]
            index_roc = index_df['close'].pct_change(10).iloc[-1]
            return stock_roc - index_roc # Excess Return
        except:
            return 0.0

    def get_news_sentiment(self):
        # Simulated
        return 0.5 # Neutral to Positive

    def check_time_filter(self):
        """Avoid trading during low volume lunch hours (12:00 - 13:00)."""
        now = datetime.now()
        if 12 <= now.hour < 13:
            return False
        return True

    def run(self):
        self.logger.info(f"Starting ML Momentum Strategy for {self.symbol} (Sector: {self.sector})")

        while True:
            if not is_market_open():
                time.sleep(60)
                continue

            # Time Filter
            if not self.check_time_filter():
                # If we have a position, we might hold, but no new entries
                if not (self.pm and self.pm.has_position()):
                    self.logger.info("Lunch hour (12:00-13:00). Skipping new entries.")
                    time.sleep(300)
                    continue

            try:
                # 1. Fetch Stock Data
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

                df = self.client.history(symbol=self.symbol, interval="15m",
                                    start_date=start_date, end_date=end_date)

                if df.empty or len(df) < 50:
                    time.sleep(60)
                    continue

                # 2. Fetch Index/Sector Data
                # Fetch NIFTY 50 for broad market RS
                nifty_df = self.client.history(symbol="NIFTY 50", interval="15m",
                                          start_date=start_date, end_date=end_date)

                # Fetch Sector for Sector Momentum Overlay
                sector_df = self.client.history(symbol=self.sector, interval="15m",
                                           start_date=start_date, end_date=end_date)

                # 3. Indicators
                df['roc'] = df['close'].pct_change(periods=10)

                # RSI
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs_val = gain / loss
                df['rsi'] = 100 - (100 / (1 + rs_val))

                # SMA for Trend
                df['sma50'] = df['close'].rolling(50).mean()

                last = df.iloc[-1]
                current_price = last['close']

                # Relative Strength vs NIFTY
                rs_excess = self.calculate_relative_strength(df, nifty_df)

                # Sector Momentum Overlay (Stock ROC vs Sector ROC)
                sector_outperformance = 0.0
                if not sector_df.empty:
                    try:
                         sector_roc = sector_df['close'].pct_change(10).iloc[-1]
                         sector_outperformance = last['roc'] - sector_roc
                    except: pass
                else:
                    sector_outperformance = 0.001 # Assume positive if missing to not block

                # News Sentiment
                sentiment = self.get_news_sentiment()

                # Manage Position
                if self.pm and self.pm.has_position():
                    pnl = self.pm.get_pnl(current_price)
                    entry = self.pm.entry_price

                    if (self.pm.position > 0 and current_price < entry * (1 - self.stop_pct/100)):
                        self.logger.info(f"Stop Loss Hit. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL')

                    # Exit if Momentum Fades (RSI < 50)
                    elif (self.pm.position > 0 and last['rsi'] < 50):
                         self.logger.info(f"Momentum Faded (RSI < 50). Exit. PnL: {pnl}")
                         self.pm.update_position(abs(self.pm.position), current_price, 'SELL')

                    time.sleep(60)
                    continue

                # Entry Logic
                # ROC > Threshold
                # RSI > 55
                # Relative Strength > 0 (Outperforming NIFTY)
                # Sector Outperformance > 0 (Outperforming Sector)
                # Price > SMA50 (Uptrend)
                # Sentiment > 0 (Not Negative)

                if (last['roc'] > self.roc_threshold and
                    last['rsi'] > 55 and
                    rs_excess > 0 and
                    sector_outperformance > 0 and
                    current_price > last['sma50'] and
                    sentiment >= 0):

                    # Volume check
                    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                    if last['volume'] > avg_vol * 0.5: # At least decent volume
                        self.logger.info(f"Strong Momentum Signal (ROC: {last['roc']:.3f}, RS: {rs_excess:.3f}). BUY.")
                        self.pm.update_position(100, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}")
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description='ML Momentum Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, default='demo_key', help='API Key')
    parser.add_argument('--threshold', type=float, default=0.01, help='ROC Threshold')
    parser.add_argument('--sector', type=str, default='NIFTY 50', help='Sector Benchmark')

    args = parser.parse_args()

    strategy = MLMomentumStrategy(args.symbol, args.api_key, args.port, threshold=args.threshold, sector=args.sector)
    strategy.run()

if __name__ == "__main__":
    run_strategy()
