#!/usr/bin/env python3
"""
My NSE Strategy
Mean Reversion strategy using RSI and Bollinger Bands.
Buy when Close < Lower BB and RSI < 30.
Sell when Close > Upper BB or RSI > 70.
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
    from trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi, calculate_bollinger_bands
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi, calculate_bollinger_bands
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi, calculate_bollinger_bands
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            normalize_symbol = lambda s: s
            is_market_open = lambda exchange='NSE': True
            calculate_rsi = lambda s, p=14: pd.Series([50]*len(s), index=s.index)
            calculate_bollinger_bands = lambda s, w=20, n=2: (pd.Series([0]*len(s), index=s.index), pd.Series([0]*len(s), index=s.index), pd.Series([0]*len(s), index=s.index))

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
        self.param1 = kwargs.get('param1', 30.0) # Used as RSI oversold threshold
        self.rsi_overbought = kwargs.get('rsi_overbought', 70.0)
        self.rsi_period = kwargs.get('rsi_period', 14)
        self.bb_window = kwargs.get('bb_window', 20)
        self.bb_std = kwargs.get('bb_std', 2.0)

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < self.bb_window:
            return 'HOLD', 0.0, {}

        # Calculate your indicators here
        df['RSI'] = calculate_rsi(df['close'], period=self.rsi_period)
        sma, upper_bb, lower_bb = calculate_bollinger_bands(df['close'], window=self.bb_window, num_std=self.bb_std)
        df['Upper_BB'] = upper_bb
        df['Lower_BB'] = lower_bb

        last = df.iloc[-1]

        # Your entry logic: Mean reversion. Buy when Close < Lower BB AND RSI < 30
        if last['close'] < last['Lower_BB'] and last['RSI'] < self.param1:
            return 'BUY', 1.0, {'reason': 'entry_signal', 'price': last['close']}

        # Exit signal generated via SELL here in calculate_signal for backtesting
        if last['close'] > last['Upper_BB'] or last['RSI'] > self.rsi_overbought:
            return 'SELL', 1.0, {'reason': 'exit_signal', 'price': last['close']}

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting strategy for {self.symbol}")

        while True:
            exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

            if not is_market_open(exchange=exchange):
                time.sleep(60)
                continue

            try:
                # Fetch historical data
                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",
                    exchange=exchange,
                    start_date=datetime.now().strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < self.bb_window:
                    time.sleep(60)
                    continue

                # Calculate indicators
                df['RSI'] = calculate_rsi(df['close'], period=self.rsi_period)
                sma, upper_bb, lower_bb = calculate_bollinger_bands(df['close'], window=self.bb_window, num_std=self.bb_std)
                df['Upper_BB'] = upper_bb
                df['Lower_BB'] = lower_bb

                last = df.iloc[-1]
                current_price = last['close']

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic: Close > Upper BB OR RSI > 70
                    pnl = self.pm.get_pnl(current_price)

                    if last['close'] > last['Upper_BB'] or last['RSI'] > self.rsi_overbought:
                        self.logger.info(f"Exiting position. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic: Close < Lower BB AND RSI < 30
                    if last['close'] < last['Lower_BB'] and last['RSI'] < self.param1:
                        # Fixed quantity for standalone script example if no adaptive logic defined
                        qty = 1
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
    # Add your custom parameters
    parser.add_argument('--param1', type=float, default=30.0, help='Parameter 1 (RSI Oversold Level)')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required")
        return

    strategy = MyNSEStrategy(
        args.symbol,
        api_key,
        args.port,
        param1=args.param1
    )
    strategy.run()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {'param1': 30.0}
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
