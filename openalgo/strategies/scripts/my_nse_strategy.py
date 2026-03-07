#!/usr/bin/env python3
"""
My NSE Strategy
Custom NSE trading strategy using RSI and Bollinger Bands for mean reversion.
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
            is_market_open = lambda exchange='NSE': True

class MyNSEStrategy:
    def __init__(self, symbol, api_key, port, **kwargs):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)

        # Setup Logger
        self.logger = logging.getLogger(f"NSE_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # Strategy parameters from kwargs
        self.param1 = kwargs.get('param1', 30.0)
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.bb_period = int(kwargs.get('bb_period', 20))
        self.bb_std = float(kwargs.get('bb_std', 2.0))

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_bollinger_bands(self, series, window=20, num_std=2):
        sma = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        upper_band = sma + (std * num_std)
        lower_band = sma - (std * num_std)
        return sma, upper_band, lower_band

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.rsi_period, self.bb_period):
            return 'HOLD', 0.0, {}

        try:
            df = df.copy()
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            df['sma'], df['upper'], df['lower'] = self.calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
        except Exception as e:
            self.logger.error(f"Indicator calculation error: {e}")
            return 'HOLD', 0.0, {}

        last = df.iloc[-1]

        # Entry logic
        # Buy when Close < Lower Band AND RSI < param1 (default 30)
        if last['close'] < last['lower'] and last['rsi'] < self.param1:
            return 'BUY', 1.0, {'reason': 'oversold_entry', 'price': last['close']}

        # Sell when Close > Upper Band OR RSI > (100 - param1)
        if last['close'] > last['upper'] or last['rsi'] > (100 - self.param1):
            return 'SELL', 1.0, {'reason': 'overbought_exit', 'price': last['close']}

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting strategy for {self.symbol}")

        # Determine exchange (NSE for stocks, NSE_INDEX for indices)
        exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

        while True:
            if not is_market_open(exchange=exchange):
                time.sleep(60)
                continue

            try:
                # Fetch historical data
                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",
                    exchange=exchange,
                    start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < max(self.rsi_period, self.bb_period):
                    time.sleep(60)
                    continue

                # Calculate indicators
                try:
                    df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
                    df['sma'], df['upper'], df['lower'] = self.calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
                except Exception as e:
                    self.logger.error(f"Indicator calculation error: {e}")
                    time.sleep(60)
                    continue

                last = df.iloc[-1]
                current_price = last['close']

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    # Exit when Close > Upper Band OR RSI > (100 - param1)
                    if current_price > last['upper'] or last['rsi'] > (100 - self.param1):
                        self.logger.info(f"Exiting position. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    # Buy when Close < Lower Band AND RSI < param1
                    if current_price < last['lower'] and last['rsi'] < self.param1:
                        qty = 1  # Base quantity
                        self.logger.info(f"Entry signal detected. Buying {qty} at {current_price}")
                        self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)  # Sleep between iterations

def run_strategy():
    parser = argparse.ArgumentParser(description='NSE Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    # Add custom parameters
    parser.add_argument('--param1', type=float, default=30.0, help='Parameter 1')
    parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
    parser.add_argument('--bb_period', type=int, default=20, help='Bollinger Band Period')
    parser.add_argument('--bb_std', type=float, default=2.0, help='Bollinger Band Std Dev')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required")
        return

    strategy = MyNSEStrategy(
        args.symbol,
        api_key,
        args.port,
        param1=args.param1,
        rsi_period=args.rsi_period,
        bb_period=args.bb_period,
        bb_std=args.bb_std
    )
    strategy.run()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {'param1': 30.0, 'rsi_period': 14, 'bb_period': 20, 'bb_std': 2.0}
    if params:
        strat_params.update(params)

    strat = MyNSEStrategy(
        symbol=symbol or "TEST",
        api_key="dummy",
        port=5001,
        **strat_params
    )

    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.calculate_signal(df)

if __name__ == "__main__":
    run_strategy()
