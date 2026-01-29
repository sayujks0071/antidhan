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

# Add repo root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.trading_utils import is_market_open, PositionManager, APIClient
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    print("Warning: openalgo package not found or imports failed.")
    APIClient = None
    PositionManager = None
    SymbolResolver = None
    is_market_open = lambda: True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class ORBStrategy:
    def __init__(self, symbol, quantity, api_key=None, host=None, range_mins=15):
        self.symbol = symbol
        self.quantity = quantity
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY')
        if not self.api_key:
             raise ValueError("API Key must be provided via --api_key or OPENALGO_APIKEY env var")

        self.host = host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
        self.range_mins = range_mins

        self.logger = logging.getLogger(f"ORB_{symbol}")
        self.client = APIClient(api_key=self.api_key, host=self.host)
        self.pm = PositionManager(symbol) if PositionManager else None

        self.orb_high = 0
        self.orb_low = 0
        self.orb_set = False
        self.orb_vol_avg = 0

    def get_previous_close(self):
        try:
            end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            df = self.client.history(symbol=self.symbol, interval="day", start_date=start, end_date=end)
            if not df.empty: return df.iloc[-1]['close']
        except: pass
        return 0

    def calculate_signals(self, df):
        """
        Backtest logic: Process a DataFrame and return signals.
        """
        signals = []
        if df.empty or len(df) < self.range_mins:
            return signals

        # Calculate ORB on the first 'range_mins' candles
        orb_df = df.iloc[:self.range_mins]
        orb_high = orb_df['high'].max()
        orb_low = orb_df['low'].min()
        orb_vol_avg = orb_df['volume'].mean()

        position = 0

        for i in range(self.range_mins, len(df)):
            candle = df.iloc[i]
            ts = candle['datetime'] if 'datetime' in candle else candle.name

            # Entry Logic
            if position == 0:
                if candle['close'] > orb_high and candle['volume'] > orb_vol_avg:
                    signals.append({'time': ts, 'side': 'BUY', 'price': candle['close']})
                    position = 1
                elif candle['close'] < orb_low and candle['volume'] > orb_vol_avg:
                    signals.append({'time': ts, 'side': 'SELL', 'price': candle['close']})
                    position = -1

            # Exit Logic (Simple EOD or Reverse)
            # For simplicity, if we are long and close < low, reverse?
            # Keeping it simple: One trade per day logic or hold till end.
            # Let's add a trailing stop or just exit at end.
            # If this is the last candle, exit.
            if i == len(df) - 1 and position != 0:
                 side = 'SELL' if position == 1 else 'BUY'
                 signals.append({'time': ts, 'side': side, 'price': candle['close'], 'reason': 'EOD'})
                 position = 0

        return signals

    def run(self):
        self.logger.info(f"Starting ORB Strategy for {self.symbol} ({self.range_mins} mins)")
        prev_close = self.get_previous_close()

        while True:
            try:
                if not is_market_open():
                    time.sleep(60)
                    continue

                now = datetime.now()
                market_open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
                orb_end_time = market_open_time + timedelta(minutes=self.range_mins)

                if now < market_open_time:
                    time.sleep(30)
                    continue

                # Wait for ORB to complete
                if now < orb_end_time:
                    time.sleep(30)
                    continue

                if not self.orb_set:
                    # Fetch ORB data
                    today = now.strftime("%Y-%m-%d")
                    # Using 1m candles
                    df = self.client.history(symbol=self.symbol, interval="1m", start_date=today, end_date=today)

                    if not df.empty and len(df) >= self.range_mins:
                        orb_df = df.iloc[:self.range_mins]
                        self.orb_high = orb_df['high'].max()
                        self.orb_low = orb_df['low'].min()
                        self.orb_vol_avg = orb_df['volume'].mean()

                        open_price = df.iloc[0]['open']
                        gap_pct = 0
                        if prev_close > 0:
                            gap_pct = (open_price - prev_close) / prev_close * 100

                        self.logger.info(f"ORB Set: {self.orb_high}-{self.orb_low}. Gap: {gap_pct:.2f}%")
                        self.orb_set = True
                    else:
                        time.sleep(30)
                        continue

                # Trading
                if self.orb_set and (not self.pm or not self.pm.has_position()):
                     df = self.client.history(symbol=self.symbol, interval="1m", start_date=today, end_date=today)
                     if df.empty: continue
                     last = df.iloc[-1]

                     # Breakout Up
                     if last['close'] > self.orb_high and last['volume'] > self.orb_vol_avg:
                         self.logger.info("ORB Breakout UP. BUY.")
                         if self.pm: self.pm.update_position(self.quantity, last['close'], 'BUY')

                     # Breakout Down
                     elif last['close'] < self.orb_low and last['volume'] > self.orb_vol_avg:
                         self.logger.info("ORB Breakout DOWN. SELL.")
                         if self.pm: self.pm.update_position(self.quantity, last['close'], 'SELL')

            except Exception as e:
                self.logger.error(f"Error: {e}")
                time.sleep(60)

            time.sleep(10)

def run_strategy():
    parser = argparse.ArgumentParser(description="ORB Strategy")
    parser.add_argument("--symbol", type=str, help="Symbol (Direct)")
    parser.add_argument("--underlying", type=str, help="Underlying Asset (e.g. NIFTY)")
    parser.add_argument("--type", type=str, default="EQUITY", help="Instrument Type (EQUITY, FUT, OPT)")
    parser.add_argument("--exchange", type=str, default="NSE", help="Exchange")
    parser.add_argument("--quantity", type=int, default=10, help="Qty")
    parser.add_argument("--api_key", type=str, default='demo_key', help="API Key")
    parser.add_argument("--host", type=str, default='http://127.0.0.1:5001', help="Host")
    parser.add_argument("--minutes", type=int, default=15, help="ORB Duration")

    args = parser.parse_args()

    symbol = args.symbol
    if not symbol and args.underlying:
        if SymbolResolver:
            resolver = SymbolResolver()
            config = {
                'underlying': args.underlying,
                'type': args.type,
                'exchange': args.exchange
            }
            res = resolver.resolve(config)
            if isinstance(res, dict): # Options return dict
                symbol = res.get('sample_symbol')
            else:
                symbol = res
            print(f"Resolved {args.underlying} -> {symbol}")
        else:
            print("SymbolResolver not available")
            return

    if not symbol:
        print("Error: Must provide --symbol or --underlying")
        return

    strategy = ORBStrategy(symbol, args.quantity, args.api_key, args.host, range_mins=args.minutes)
    strategy.run()

if __name__ == "__main__":
    run_strategy()
