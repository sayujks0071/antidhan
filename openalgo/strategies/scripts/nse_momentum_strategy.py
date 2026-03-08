#!/usr/bin/env python3
"""
NSE Momentum Strategy
A momentum strategy for NSE using RSI and Bollinger Bands.
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

class NSEMomentumStrategy:
    def __init__(self, symbol, api_key, port, **kwargs):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host) if APIClient else None

        # Setup Logger
        self.logger = logging.getLogger(f"NSE_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(ch)

        # Strategy parameters from kwargs
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.bb_period = int(kwargs.get('bb_period', 20))
        self.bb_std = float(kwargs.get('bb_std', 2.0))
        self.quantity = int(kwargs.get('quantity', 1))

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.rsi_period, self.bb_period):
            return 'HOLD', 0.0, {}

        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # Calculate Bollinger Bands
        df['sma'] = df['close'].rolling(window=self.bb_period).mean()
        df['std'] = df['close'].rolling(window=self.bb_period).std()
        df['upper_bb'] = df['sma'] + (df['std'] * self.bb_std)
        df['lower_bb'] = df['sma'] - (df['std'] * self.bb_std)

        if len(df) < 2:
            return 'HOLD', 0.0, {}

        last = df.iloc[-1]
        prev = df.iloc[-2]

        current_price = last['close']
        current_rsi = last['rsi']
        upper_bb = last['upper_bb']
        sma = last['sma']

        # Entry logic: Close crosses above Upper BB and RSI > 60
        entry_condition = (prev['close'] <= prev['upper_bb']) and (current_price > upper_bb) and (current_rsi > 60)

        # Exit logic: Close crosses below SMA or RSI < 40
        exit_condition = (prev['close'] >= prev['sma'] and current_price < sma) or (current_rsi < 40)

        if entry_condition:
            return 'BUY', float(self.quantity), {'reason': 'entry_signal', 'price': current_price}
        elif exit_condition:
            return 'EXIT_BUY', 0.0, {'reason': 'exit_signal', 'price': current_price}

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting strategy for {self.symbol}")

        while True:
            if not is_market_open():
                time.sleep(60)
                continue

            try:
                # Determine exchange (NSE for stocks, NSE_INDEX for indices)
                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

                # Fetch historical data
                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",
                    exchange=exchange,
                    start_date=datetime.now().strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df is None or df.empty or len(df) < max(self.rsi_period, self.bb_period):
                    time.sleep(60)
                    continue

                # Calculate indicators
                # RSI
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
                rs = gain / loss
                df['rsi'] = 100 - (100 / (1 + rs))

                # Bollinger Bands
                df['sma'] = df['close'].rolling(window=self.bb_period).mean()
                df['std'] = df['close'].rolling(window=self.bb_period).std()
                df['upper_bb'] = df['sma'] + (df['std'] * self.bb_std)
                df['lower_bb'] = df['sma'] - (df['std'] * self.bb_std)

                last = df.iloc[-1]
                prev = df.iloc[-2]
                current_price = last['close']
                current_rsi = last['rsi']
                upper_bb = last['upper_bb']
                sma = last['sma']

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    exit_condition = (prev['close'] >= prev['sma'] and current_price < sma) or (current_rsi < 40)

                    if exit_condition:
                        self.logger.info(f"Exiting position. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    entry_condition = (prev['close'] <= prev['upper_bb']) and (current_price > upper_bb) and (current_rsi > 60)

                    if entry_condition:
                        qty = self.quantity
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

    # Custom parameters
    parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
    parser.add_argument('--bb_period', type=int, default=20, help='Bollinger Bands Period')
    parser.add_argument('--bb_std', type=float, default=2.0, help='Bollinger Bands Std Dev')
    parser.add_argument('--quantity', type=int, default=1, help='Trade Quantity')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required")
        return

    strategy = NSEMomentumStrategy(
        args.symbol,
        api_key,
        args.port,
        rsi_period=args.rsi_period,
        bb_period=args.bb_period,
        bb_std=args.bb_std,
        quantity=args.quantity
    )
    strategy.run()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0,
        'quantity': 1
    }
    if params:
        strat_params.update(params)

    strat = NSEMomentumStrategy(
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
