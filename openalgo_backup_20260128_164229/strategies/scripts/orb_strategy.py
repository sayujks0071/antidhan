#!/usr/bin/env python3
"""
ORB Strategy (Opening Range Breakout)
Enhanced with Pre-Market Gap Analysis, Volume Confirmation, Trend Filter (EMA50), and ATR Risk Management.
"""
import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
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
        self.trend_bullish = True  # Default to True
        self.gap_pct = 0.0
        self.atr = 0.0
        self.skip_trade = False

        # Risk State
        self.sl = 0.0
        self.tp = 0.0

    def calculate_atr(self, df, period=14):
        """Calculate ATR"""
        high = df['high']
        low = df['low']
        close = df['close']
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    def fetch_daily_context(self):
        """Fetch Previous Close and Daily Trend (EMA50)"""
        try:
            # Look back enough days for EMA50 calculation and to handle weekends/holidays
            today = datetime.now().date()
            end = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            start = (today - timedelta(days=100)).strftime("%Y-%m-%d")  # Need enough data for EMA50

            df = self.client.history(symbol=self.symbol, interval="day", start_date=start, end_date=end)

            if not df.empty and len(df) > 50:
                df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
                last_close = df.iloc[-1]['close']
                last_ema = df.iloc[-1]['ema50']

                self.trend_bullish = last_close > last_ema
                prev_close = df.iloc[-1]['close']  # Most recent completed trading day

                self.atr = self.calculate_atr(df)
                return prev_close
            elif not df.empty:
                # Not enough data for EMA50, but return previous close
                return df.iloc[-1]['close']
        except Exception as e:
            self.logger.error(f"Error fetching context: {e}")
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
        prev_close = self.fetch_daily_context()
        self.logger.info(f"Context: Trend Bullish={self.trend_bullish}, Prev Close={prev_close}, ATR={self.atr:.2f}")

        while True:
            try:
                # Basic market check
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
                    today = now.strftime("%Y-%m-%d")
                    df = self.client.history(symbol=self.symbol, interval="1m", start_date=today, end_date=today)

                    if not df.empty and len(df) >= self.range_mins:
                        orb_df = df.iloc[:self.range_mins]
                        self.orb_high = orb_df['high'].max()
                        self.orb_low = orb_df['low'].min()
                        self.orb_vol_avg = orb_df['volume'].mean()

                        open_price = df.iloc[0]['open']
                        if prev_close > 0:
                            self.gap_pct = (open_price - prev_close) / prev_close * 100

                        self.logger.info(f"ORB Set: {self.orb_high}-{self.orb_low}. Gap: {self.gap_pct:.2f}%. Trend Bullish: {self.trend_bullish}")

                        # Gap Analysis - skip if gap is too large
                        if abs(self.gap_pct) > 2.0:
                            self.logger.info("Gap > 2%. Skipping ORB trades due to volatility risk.")
                            self.skip_trade = True

                        self.orb_set = True
                    else:
                        time.sleep(30)
                        continue

                # Trading Logic
                today = now.strftime("%Y-%m-%d")
                df = self.client.history(symbol=self.symbol, interval="1m", start_date=today, end_date=today)
                if df.empty:
                    time.sleep(10)
                    continue
                last = df.iloc[-1]

                if self.pm and self.pm.has_position():
                    # Check Exits
                    if self.sl > 0 and self.tp > 0:
                        pos_size = self.pm.position

                        if pos_size > 0: # Long
                            if last['close'] <= self.sl:
                                self.logger.info(f"SL Hit: {last['close']}")
                                self.pm.update_position(abs(pos_size), last['close'], 'SELL')
                                self.sl = 0; self.tp = 0
                            elif last['close'] >= self.tp:
                                self.logger.info(f"TP Hit: {last['close']}")
                                self.pm.update_position(abs(pos_size), last['close'], 'SELL')
                                self.sl = 0; self.tp = 0
                        elif pos_size < 0: # Short
                            if last['close'] >= self.sl:
                                self.logger.info(f"SL Hit: {last['close']}")
                                self.pm.update_position(abs(pos_size), last['close'], 'BUY')
                                self.sl = 0; self.tp = 0
                            elif last['close'] <= self.tp:
                                self.logger.info(f"TP Hit: {last['close']}")
                                self.pm.update_position(abs(pos_size), last['close'], 'BUY')
                                self.sl = 0; self.tp = 0

                elif self.orb_set and not self.skip_trade:
                     # Improved Logic:
                     is_long = last['close'] > self.orb_high and last['volume'] > self.orb_vol_avg
                     is_short = last['close'] < self.orb_low and last['volume'] > self.orb_vol_avg

                     # Filters
                     if is_long:
                         if not self.trend_bullish:
                             # self.logger.info("Skipping Long: Trend is Bearish")
                             pass
                         elif self.gap_pct > 0.5:
                             # self.logger.info(f"Skipping Long: Large Gap Up ({self.gap_pct:.2f}%)")
                             pass
                         else:
                             self.logger.info("ORB Breakout UP. BUY.")
                             # SL/TP
                             self.sl = last['close'] - (1.5 * self.atr)
                             self.tp = last['close'] + (3.0 * self.atr)
                             self.logger.info(f"SL: {self.sl:.2f}, TP: {self.tp:.2f}")
                             if self.pm: self.pm.update_position(self.quantity, last['close'], 'BUY')

                     elif is_short:
                         if self.trend_bullish:
                             pass
                         elif self.gap_pct < -0.5:
                             pass
                         else:
                             self.logger.info("ORB Breakout DOWN. SELL.")
                             self.sl = last['close'] + (1.5 * self.atr)
                             self.tp = last['close'] - (3.0 * self.atr)
                             self.logger.info(f"SL: {self.sl:.2f}, TP: {self.tp:.2f}")
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
    parser.add_argument("--api_key", type=str, default=None, help="API Key (or set OPENALGO_APIKEY)")
    parser.add_argument("--host", type=str, default=None, help="Host URL (or set OPENALGO_HOST)")
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
