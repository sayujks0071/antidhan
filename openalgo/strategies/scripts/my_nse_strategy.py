#!/usr/bin/env python3
"""
Custom NSE trading strategy
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

def calculate_rsi(series, period=14):
    """Calculate Relative Strength Index."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


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
        # Add more parameters as needed

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(20, self.param1 + 1):
            return 'HOLD', 0.0, {}

        # Calculate your indicators here
        try:
            df['rsi'] = calculate_rsi(df['close'], period=int(self.param1))
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            return 'HOLD', 0.0, {}

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Your entry logic: RSI crossover below 30
        if prev['rsi'] <= 30 and last['rsi'] > 30:
            return 'BUY', 1.0, {'reason': 'rsi_crossover_up', 'price': last['close']}

        # Exit logic for backtesting (if generating exits): RSI crossunder 70
        if prev['rsi'] >= 70 and last['rsi'] < 70:
            return 'SELL', 1.0, {'reason': 'rsi_crossover_down', 'price': last['close']}

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
                    interval="5m",  # or "1m", "15m", "D", etc.
                    exchange=exchange,
                    start_date=datetime.now().strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < 20:
                    time.sleep(60)
                    continue

                # Calculate indicators
                try:
                    df['rsi'] = calculate_rsi(df['close'], period=int(self.param1))
                except Exception as e:
                    self.logger.error(f"Error calculating indicators: {e}")
                    time.sleep(60)
                    continue

                if len(df) < 2:
                    time.sleep(60)
                    continue

                last = df.iloc[-1]
                prev = df.iloc[-2]
                current_price = last['close']

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    # Exit Condition: RSI crosses above 70 or falls below it from above
                    exit_condition = prev['rsi'] >= 70 and last['rsi'] < 70

                    if exit_condition:
                        self.logger.info(f"Exiting position. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    # Entry Condition: RSI crosses above 30
                    entry_condition = prev['rsi'] <= 30 and last['rsi'] > 30

                    if entry_condition:
                        qty = 1 # Simple quantity of 1 for stocks
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
    parser.add_argument('--param1', type=float, default=30.0, help='Parameter 1')

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
