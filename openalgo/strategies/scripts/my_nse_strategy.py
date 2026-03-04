#!/usr/bin/env python3
"""
My NSE Strategy
Custom NSE mean reversion trading strategy using RSI and Bollinger Bands.
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
            is_market_open = lambda exchange="NSE": True

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

    def calculate_bollinger_bands(self, series, window=20, num_std=2.0):
        sma = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        return sma, upper, lower

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

        # Calculate your indicators here
        try:
            from trading_utils import calculate_rsi, calculate_bollinger_bands
            df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
            df['sma'], df['upper'], df['lower'] = calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
        except Exception:
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            df['sma'], df['upper'], df['lower'] = self.calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)

        last = df.iloc[-1]
        close = last['close']
        rsi = last['rsi']
        lower = last['lower']
        upper = last['upper']

        # Your entry logic
        if close < lower and rsi < self.param1:
            return 'BUY', 1.0, {'reason': 'Oversold (RSI < 30) & Below Lower Band', 'price': close, 'rsi': rsi, 'lower_band': lower}

        if close > upper or rsi > (100 - self.param1):
            return 'SELL', 1.0, {'reason': 'Overbought (RSI > 70) or Above Upper Band', 'price': close, 'rsi': rsi, 'upper_band': upper}

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
                df = None
                if self.client:
                    df = self.client.history(
                        symbol=self.symbol,
                        interval="5m",  # or "1m", "15m", "D", etc.
                        exchange=exchange,
                        start_date=datetime.now().strftime("%Y-%m-%d"),
                        end_date=datetime.now().strftime("%Y-%m-%d")
                    )

                if df is None or df.empty or len(df) < max(self.rsi_period, self.bb_period):
                    time.sleep(60)
                    continue

                # Calculate indicators
                try:
                    from trading_utils import calculate_rsi, calculate_bollinger_bands
                    df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
                    df['sma'], df['upper'], df['lower'] = calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
                except Exception:
                    df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
                    df['sma'], df['upper'], df['lower'] = self.calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)

                last = df.iloc[-1]
                current_price = last['close']
                rsi = last['rsi']
                lower = last['lower']
                upper = last['upper']

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    if current_price > upper or rsi > (100 - self.param1):
                        self.logger.info(f"Exiting position. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    if current_price < lower and rsi < self.param1:
                        qty = 1 # [YOUR_QUANTITY_LOGIC]
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
