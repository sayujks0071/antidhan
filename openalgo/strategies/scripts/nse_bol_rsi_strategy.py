#!/usr/bin/env python3
"""
NSE Bollinger Bands + RSI Strategy
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

# 1. Core Imports (APIClient, PositionManager)
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
            print("Warning: openalgo package not found or imports failed. Using Dummy Client.")
            class APIClient:
                def __init__(self, api_key, host): pass
                def history(self, **kwargs): return pd.DataFrame()
            class PositionManager:
                def __init__(self, symbol): self.position = 0
                def has_position(self): return False
                def update_position(self, *args): pass
                def get_pnl(self, *args): return 0.0

            normalize_symbol = lambda s: s
            is_market_open = lambda: True

# 2. Indicator Imports (with Inline Fallback)
try:
    from trading_utils import calculate_rsi, calculate_bollinger_bands
except ImportError:
    try:
        from openalgo.strategies.utils.trading_utils import calculate_rsi, calculate_bollinger_bands
    except ImportError:
        def calculate_rsi(series, period=14):
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            return 100 - (100 / (1 + rs))

        def calculate_bollinger_bands(series, window=20, num_std=2):
            sma = series.rolling(window=window).mean()
            std = series.rolling(window=window).std()
            upper = sma + (std * num_std)
            lower = sma - (std * num_std)
            return sma, upper, lower

class NSEBollingerRSIStrategy:
    def __init__(self, symbol, api_key, port, **kwargs):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)

        # Setup Logger
        self.logger = logging.getLogger(f"NSE_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Check if handlers already exist to avoid duplicates
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

        # Strategy parameters from kwargs
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.bb_period = int(kwargs.get('bb_period', 20))
        self.bb_std = float(kwargs.get('bb_std', 2.0))
        self.rsi_buy = float(kwargs.get('rsi_buy', 30.0))
        self.rsi_sell = float(kwargs.get('rsi_sell', 70.0))
        self.quantity = int(kwargs.get('quantity', 1))

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.bb_period, self.rsi_period) + 2:
            return 'HOLD', 0.0, {}

        # Calculate indicators
        close = df['close']
        rsi = calculate_rsi(close, period=self.rsi_period)
        sma, upper, lower = calculate_bollinger_bands(close, window=self.bb_period, num_std=self.bb_std)

        last = df.iloc[-1]
        last_rsi = rsi.iloc[-1]
        last_close = last['close']
        last_upper = upper.iloc[-1]
        last_lower = lower.iloc[-1]
        last_sma = sma.iloc[-1]

        # Entry Logic
        # Buy: Close < Lower Band AND RSI < 30
        if last_close < last_lower and last_rsi < self.rsi_buy:
            return 'BUY', 1.0, {
                'reason': 'Oversold (BB+RSI)',
                'price': last_close,
                'rsi': last_rsi,
                'lower_band': last_lower
            }

        # Sell (Short): Close > Upper Band AND RSI > 70
        if last_close > last_upper and last_rsi > self.rsi_sell:
            return 'SELL', 1.0, {
                'reason': 'Overbought (BB+RSI)',
                'price': last_close,
                'rsi': last_rsi,
                'upper_band': last_upper
            }

        # Exit Logic (for backtesting, we might return EXIT if we held a position)
        # But calculate_signal is usually stateless for simple signals.
        # For stateful strategies, we need position info.
        # Here we just return signal.

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting NSE Bollinger RSI Strategy for {self.symbol}")
        self.logger.info(f"Params: RSI={self.rsi_period}, BB=({self.bb_period},{self.bb_std})")

        while True:
            if not is_market_open():
                self.logger.info("Market is closed. Sleeping...")
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

                if df.empty or len(df) < max(self.bb_period, self.rsi_period) + 2:
                    self.logger.info("Insufficient data, waiting...")
                    time.sleep(60)
                    continue

                # Calculate indicators
                close = df['close']
                rsi = calculate_rsi(close, period=self.rsi_period)
                sma, upper, lower = calculate_bollinger_bands(close, window=self.bb_period, num_std=self.bb_std)

                last_rsi = rsi.iloc[-1]
                current_price = close.iloc[-1]
                last_upper = upper.iloc[-1]
                last_lower = lower.iloc[-1]
                last_sma = sma.iloc[-1]

                self.logger.info(f"Price: {current_price}, RSI: {last_rsi:.2f}, BB: {last_lower:.2f}/{last_sma:.2f}/{last_upper:.2f}")

                # Position management
                if self.pm and self.pm.has_position():
                    pnl = self.pm.get_pnl(current_price)
                    position = self.pm.position

                    # Exit Logic
                    exit_signal = False
                    reason = ""

                    if position > 0: # Long Position
                        # Exit if Price > SMA (Mean Reversion)
                        if current_price >= last_sma:
                            exit_signal = True
                            reason = "Target Reached (SMA Touch)"

                    elif position < 0: # Short Position
                        # Exit if Price < SMA (Mean Reversion)
                        if current_price <= last_sma:
                            exit_signal = True
                            reason = "Target Reached (SMA Touch)"

                    if exit_signal:
                        self.logger.info(f"Exiting position. PnL: {pnl}. Reason: {reason}")
                        action = 'SELL' if position > 0 else 'BUY'
                        self.pm.update_position(abs(position), current_price, action)

                else:
                    # Entry logic
                    qty = self.quantity

                    # Buy Signal
                    if current_price < last_lower and last_rsi < self.rsi_buy:
                        self.logger.info(f"Entry signal (BUY) detected. RSI: {last_rsi:.2f} < {self.rsi_buy}")
                        self.pm.update_position(qty, current_price, 'BUY')

                    # Sell Signal
                    elif current_price > last_upper and last_rsi > self.rsi_sell:
                        self.logger.info(f"Entry signal (SELL) detected. RSI: {last_rsi:.2f} > {self.rsi_sell}")
                        self.pm.update_position(qty, current_price, 'SELL')

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)  # Sleep between iterations

def run_strategy():
    parser = argparse.ArgumentParser(description='NSE Bollinger RSI Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    # Custom parameters
    parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
    parser.add_argument('--bb_period', type=int, default=20, help='Bollinger Bands Period')
    parser.add_argument('--bb_std', type=float, default=2.0, help='Bollinger Bands Std Dev')
    parser.add_argument('--rsi_buy', type=float, default=30.0, help='RSI Buy Threshold')
    parser.add_argument('--rsi_sell', type=float, default=70.0, help='RSI Sell Threshold')
    parser.add_argument('--quantity', type=int, default=1, help='Trade Quantity')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required")
        return

    strategy = NSEBollingerRSIStrategy(
        symbol=args.symbol,
        api_key=api_key,
        port=args.port,
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
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0,
        'rsi_buy': 30.0,
        'rsi_sell': 70.0
    }
    if params:
        strat_params.update(params)

    strat = NSEBollingerRSIStrategy(
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
