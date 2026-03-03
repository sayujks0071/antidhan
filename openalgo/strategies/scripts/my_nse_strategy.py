#!/usr/bin/env python3
"""
My NSE Strategy
Custom NSE trading strategy using RSI and Bollinger Bands.
Logic: Mean reversion.
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
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.bb_period = int(kwargs.get('bb_period', 20))
        self.bb_std = float(kwargs.get('bb_std', 2.0))

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_bollinger_bands(self, series, window=20, num_std=2.0):
        sma = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        return sma, upper, lower

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.rsi_period, self.bb_period):
            return 'HOLD', 0.0, {}

        # Calculate indicators
        try:
            df = df.copy()
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            df['sma'], df['upper_bb'], df['lower_bb'] = self.calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
        except Exception as e:
            self.logger.error(f"Indicator calculation error: {e}")
            return 'HOLD', 0.0, {}

        last = df.iloc[-1]
        close = last['close']
        rsi = last['rsi']
        lower_bb = last['lower_bb']
        upper_bb = last['upper_bb']

        # Entry logic: Close < Lower BB AND RSI < 30
        if close < lower_bb and rsi < self.param1:
            return 'BUY', 1.0, {
                'reason': f'Oversold (RSI < {self.param1}) & Below Lower BB',
                'price': close,
                'rsi': rsi,
                'lower_bb': lower_bb
            }

        # Exit logic: Close > Upper BB OR RSI > 70
        if close > upper_bb or rsi > (100 - self.param1):
            return 'SELL', 1.0, {
                'reason': f'Overbought (RSI > {100 - self.param1}) or Above Upper BB',
                'price': close,
                'rsi': rsi,
                'upper_bb': upper_bb
            }

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

                if df.empty or len(df) < max(self.rsi_period, self.bb_period):
                    time.sleep(60)
                    continue

                # Generate signal
                signal, _, metadata = self.calculate_signal(df)

                last = df.iloc[-1]
                current_price = last['close']

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    if signal == 'SELL':
                        self.logger.info(f"Exiting position: {metadata['reason']}. PnL: {pnl:.2f}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    if signal == 'BUY':
                        # Default to 1 qty if PM adaptive qty isn't available, or implement custom qty logic
                        qty = 1
                        if hasattr(self.pm, 'calculate_adaptive_quantity'):
                            try:
                                qty = self.pm.calculate_adaptive_quantity(100000, 2.0, 1.0, current_price)
                                qty = max(1, qty)
                            except:
                                pass

                        self.logger.info(f"Entry signal detected: {metadata['reason']}. Buying {qty} at {current_price}")
                        if self.pm:
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
    parser.add_argument('--param1', type=float, default=30.0, help='RSI Oversold Level')
    parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
    parser.add_argument('--bb_period', type=int, default=20, help='Bollinger Band Period')
    parser.add_argument('--bb_std', type=float, default=2.0, help='Bollinger Band Std Dev')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required")
        # In a real scenario we'd exit, but we proceed to allow testing without key

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
    strat_params = {
        'param1': 30.0,
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0
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
