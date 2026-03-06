#!/usr/bin/env python3
"""
My NSE Strategy
Mean reversion strategy using RSI and Bollinger Bands for the NSE.
Entry: Close < Lower BB AND RSI < 30.
Exit: Close > Upper BB OR RSI > 70.
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
        self.client = APIClient(api_key=api_key, host=self.host) if APIClient else None

        # Setup Logger
        self.logger = logging.getLogger(f"NSE_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # Strategy parameters from kwargs
        self.param1 = kwargs.get('param1', 30.0)
        self.rsi_period = kwargs.get('rsi_period', 14)
        self.bb_period = kwargs.get('bb_period', 20)
        self.bb_std = kwargs.get('bb_std', 2.0)
        self.rsi_buy = kwargs.get('rsi_buy', 30)
        self.rsi_sell = kwargs.get('rsi_sell', 70)
        self.quantity = kwargs.get('quantity', 1)

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < 20:
            return 'HOLD', 0.0, {}

        # Calculate indicators
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        df['sma'] = df['close'].rolling(window=self.bb_period).mean()
        std = df['close'].rolling(window=self.bb_period).std()
        df['upper_bb'] = df['sma'] + (self.bb_std * std)
        df['lower_bb'] = df['sma'] - (self.bb_std * std)

        if pd.isna(df['rsi'].iloc[-1]) or pd.isna(df['lower_bb'].iloc[-1]):
             return 'HOLD', 0.0, {}

        last = df.iloc[-1]

        # Entry logic: Mean reversion. Buy if Close < Lower BB AND RSI < 30.
        if last['close'] < last['lower_bb'] and last['rsi'] < self.rsi_buy:
            return 'BUY', 1.0, {'reason': 'entry_signal', 'price': last['close']}

        # Exit logic: Sell if Close > Upper BB OR RSI > 70.
        if last['close'] > last['upper_bb'] or last['rsi'] > self.rsi_sell:
             return 'SELL', 1.0, {'reason': 'exit_signal', 'price': last['close']}

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting strategy for {self.symbol}")

        while True:
            # Determine exchange (NSE for stocks, NSE_INDEX for indices)
            exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

            if not is_market_open(exchange=exchange):
                time.sleep(60)
                continue

            try:
                # Fetch historical data
                if not self.client:
                    self.logger.error("APIClient not initialized.")
                    time.sleep(60)
                    continue

                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",
                    exchange=exchange,
                    start_date=datetime.now().strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < 20:
                    time.sleep(60)
                    continue

                # Calculate indicators
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
                rs = gain / loss
                df['rsi'] = 100 - (100 / (1 + rs))

                df['sma'] = df['close'].rolling(window=self.bb_period).mean()
                std = df['close'].rolling(window=self.bb_period).std()
                df['upper_bb'] = df['sma'] + (self.bb_std * std)
                df['lower_bb'] = df['sma'] - (self.bb_std * std)

                if pd.isna(df['rsi'].iloc[-1]) or pd.isna(df['lower_bb'].iloc[-1]):
                    time.sleep(60)
                    continue

                last = df.iloc[-1]
                current_price = last['close']

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    if current_price > last['upper_bb'] or last['rsi'] > self.rsi_sell:
                        self.logger.info(f"Exiting position. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    if current_price < last['lower_bb'] and last['rsi'] < self.rsi_buy:
                        qty = self.quantity
                        self.logger.info(f"Entry signal detected. Buying {qty} at {current_price}")
                        if self.pm:
                            self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)  # Sleep between iterations

def run_strategy():
    parser = argparse.ArgumentParser(description='My NSE Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')
    # Add your custom parameters
    parser.add_argument('--param1', type=float, default=30.0, help='Parameter 1')
    parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
    parser.add_argument('--bb_period', type=int, default=20, help='Bollinger Bands Period')
    parser.add_argument('--bb_std', type=float, default=2.0, help='Bollinger Bands Std Dev')
    parser.add_argument('--rsi_buy', type=float, default=30.0, help='RSI Buy Threshold')
    parser.add_argument('--rsi_sell', type=float, default=70.0, help='RSI Sell Threshold')
    parser.add_argument('--quantity', type=int, default=1, help='Quantity')

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
        bb_std=args.bb_std,
        rsi_buy=args.rsi_buy,
        rsi_sell=args.rsi_sell,
        quantity=args.quantity
    )
    strategy.run()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'param1': 30.0,
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0,
        'rsi_buy': 30.0,
        'rsi_sell': 70.0,
        'quantity': 1
    }
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
