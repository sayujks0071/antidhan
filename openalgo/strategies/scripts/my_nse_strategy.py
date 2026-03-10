#!/usr/bin/env python3
"""
My NSE Strategy
An EMA Crossover and RSI Strategy for NSE Equities.
Entry: Buy when 9 EMA crosses above 21 EMA AND RSI > param1 (default 30).
Exit: Sell when 9 EMA crosses below 21 EMA.
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
    """Calculate RSI for a pandas series."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

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
        self.ema_fast = kwargs.get('ema_fast', 9)
        self.ema_slow = kwargs.get('ema_slow', 21)
        self.rsi_period = kwargs.get('rsi_period', 14)

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.ema_slow, self.rsi_period) + 1:
            return 'HOLD', 0.0, {}

        # Calculate your indicators here
        df['ema_fast'] = df['close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.ema_slow, adjust=False).mean()
        df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)

        prev = df.iloc[-2]
        last = df.iloc[-1]

        # Your entry logic
        # 9 EMA crosses above 21 EMA and RSI > param1
        crossover_bullish = (prev['ema_fast'] <= prev['ema_slow']) and (last['ema_fast'] > last['ema_slow'])
        if crossover_bullish and last['rsi'] > self.param1:
            return 'BUY', 1.0, {'reason': 'ema_crossover_up_rsi', 'price': last['close']}

        crossover_bearish = (prev['ema_fast'] >= prev['ema_slow']) and (last['ema_fast'] < last['ema_slow'])
        if crossover_bearish:
            return 'SELL', 1.0, {'reason': 'ema_crossover_down', 'price': last['close']}

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting strategy for {self.symbol}")

        while True:
            if not is_market_open():
                time.sleep(60)
                continue

            if not self.client:
                self.logger.error("APIClient not initialized. Exiting.")
                break

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

                if df.empty or len(df) < max(self.ema_slow, self.rsi_period) + 1:
                    time.sleep(60)
                    continue

                # Calculate indicators
                df['ema_fast'] = df['close'].ewm(span=self.ema_fast, adjust=False).mean()
                df['ema_slow'] = df['close'].ewm(span=self.ema_slow, adjust=False).mean()
                df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)

                prev = df.iloc[-2]
                last = df.iloc[-1]
                current_price = last['close']

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    # Exit condition: 9 EMA crosses below 21 EMA
                    crossover_bearish = (prev['ema_fast'] >= prev['ema_slow']) and (last['ema_fast'] < last['ema_slow'])

                    if crossover_bearish:
                        self.logger.info(f"Exiting position. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    # 9 EMA crosses above 21 EMA and RSI > param1
                    crossover_bullish = (prev['ema_fast'] <= prev['ema_slow']) and (last['ema_fast'] > last['ema_slow'])

                    if crossover_bullish and last['rsi'] > self.param1:
                        # Base quantity of 1 for equity strategies (or use custom logic here)
                        qty = 1
                        if self.pm:
                            try:
                                # Example: simple static quantity if adaptive isn't easily accessible without base class
                                qty = 100
                            except Exception:
                                pass

                        self.logger.info(f"Entry signal detected. Buying {qty} at {current_price}")
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
