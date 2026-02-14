#!/usr/bin/env python3
"""
NSE MA Crossover Strategy
Simple Moving Average Crossover for NSE stocks.
Entry: Buy when SMA 20 crosses above SMA 50.
Exit: Sell when SMA 20 crosses below SMA 50.
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
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')
sys.path.insert(0, utils_dir)

try:
    from trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            normalize_symbol = lambda s: s
            is_market_open = lambda: True

class NSEMaCrossoverStrategy:
    def __init__(self, symbol, api_key, port, **kwargs):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host) if APIClient else None

        # Setup Logger
        self.logger = logging.getLogger(f"NSE_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Clear existing handlers
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # Strategy parameters from kwargs
        self.short_window = int(kwargs.get('short_window', 20))
        self.long_window = int(kwargs.get('long_window', 50))
        self.quantity = int(kwargs.get('quantity', 1))

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < self.long_window + 5:
            return 'HOLD', 0.0, {}

        # Calculate indicators
        df['short_mavg'] = df['close'].rolling(window=self.short_window, min_periods=1).mean()
        df['long_mavg'] = df['close'].rolling(window=self.long_window, min_periods=1).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Entry logic: Buy if Short MA crosses above Long MA (Golden Cross)
        bullish_crossover = (prev['short_mavg'] <= prev['long_mavg']) and (last['short_mavg'] > last['long_mavg'])

        if bullish_crossover:
            return 'BUY', 1.0, {
                'reason': 'MA Crossover (Golden Cross)',
                'price': last['close'],
                'short_mavg': last['short_mavg'],
                'long_mavg': last['long_mavg']
            }

        # Exit logic: Sell if Short MA crosses below Long MA (Death Cross)
        bearish_crossover = (prev['short_mavg'] >= prev['long_mavg']) and (last['short_mavg'] < last['long_mavg'])

        if bearish_crossover:
             return 'SELL', 1.0, {
                'reason': 'MA Crossover (Death Cross)',
                'price': last['close'],
                'short_mavg': last['short_mavg'],
                'long_mavg': last['long_mavg']
            }

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting NSE MA Crossover Strategy for {self.symbol}")
        self.logger.info(f"Params: Short={self.short_window}, Long={self.long_window}, Qty={self.quantity}")

        while True:
            if not is_market_open():
                self.logger.info("Market is closed. Sleeping...")
                time.sleep(60)
                continue

            try:
                # Determine exchange (NSE for stocks, NSE_INDEX for indices)
                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

                # Fetch historical data
                # Fetch enough data for the long window
                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",
                    exchange=exchange,
                    start_date=datetime.now().strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < self.long_window:
                    self.logger.info("Waiting for sufficient data...")
                    time.sleep(60)
                    continue

                # Calculate indicators locally
                df['short_mavg'] = df['close'].rolling(window=self.short_window, min_periods=1).mean()
                df['long_mavg'] = df['close'].rolling(window=self.long_window, min_periods=1).mean()

                last = df.iloc[-1]
                prev = df.iloc[-2]
                current_price = last['close']
                current_short = last['short_mavg']
                current_long = last['long_mavg']

                self.logger.info(f"Price: {current_price}, SMA{self.short_window}: {current_short:.2f}, SMA{self.long_window}: {current_long:.2f}")

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    # Exit on Death Cross
                    bearish_crossover = (prev['short_mavg'] >= prev['long_mavg']) and (last['short_mavg'] < last['long_mavg'])

                    if bearish_crossover:
                        self.logger.info(f"Exiting position (Death Cross). PnL: {pnl:.2f}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    # Enter on Golden Cross
                    bullish_crossover = (prev['short_mavg'] <= prev['long_mavg']) and (last['short_mavg'] > last['long_mavg'])

                    if bullish_crossover:
                        qty = self.quantity
                        self.logger.info(f"Entry signal detected (Golden Cross). Buying {qty} at {current_price}")
                        self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)  # Sleep between iterations

def run_strategy():
    parser = argparse.ArgumentParser(description='NSE MA Crossover Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol (e.g., RELIANCE)')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    # Custom parameters
    parser.add_argument('--short_window', type=int, default=20, help='Short Moving Average Window')
    parser.add_argument('--long_window', type=int, default=50, help='Long Moving Average Window')
    parser.add_argument('--quantity', type=int, default=1, help='Trade Quantity')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required. Set OPENALGO_APIKEY env var or pass --api_key")
        return

    strategy = NSEMaCrossoverStrategy(
        args.symbol,
        api_key,
        args.port,
        short_window=args.short_window,
        long_window=args.long_window,
        quantity=args.quantity
    )
    strategy.run()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    """
    Generate signal for backtesting.
    """
    strat_params = {
        'short_window': 20,
        'long_window': 50
    }
    if params:
        strat_params.update(params)

    strat = NSEMaCrossoverStrategy(
        symbol=symbol or "TEST",
        api_key="dummy",
        port=5001,
        **strat_params
    )

    # Disable logging for backtest
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.calculate_signal(df)

if __name__ == "__main__":
    run_strategy()
