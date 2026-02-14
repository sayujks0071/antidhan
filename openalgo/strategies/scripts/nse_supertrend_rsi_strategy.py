#!/usr/bin/env python3
"""
NSE SuperTrend + RSI Strategy
Combines SuperTrend (Trend Following) and RSI (Momentum) for entry signals.
Exits on Trend Reversal (SuperTrend flips).
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
project_root = os.path.dirname(strategies_dir) # openalgo
utils_dir = os.path.join(strategies_dir, 'utils')
sys.path.insert(0, utils_dir)
sys.path.insert(0, project_root)

try:
    from trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_supertrend, calculate_rsi
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_supertrend, calculate_rsi
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_supertrend, calculate_rsi
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            normalize_symbol = lambda s: s
            is_market_open = lambda: True
            calculate_supertrend = lambda df, period, multiplier: (pd.Series([0]*len(df)), pd.Series([1]*len(df)))
            calculate_rsi = lambda s, p: pd.Series([50]*len(s))

class NSESuperTrendRSIStrategy:
    def __init__(self, symbol, api_key, port, **kwargs):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)

        # Setup Logger
        self.logger = logging.getLogger(f"NSE_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Avoid duplicate handlers if re-instantiated
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

        # Strategy parameters from kwargs
        self.supertrend_period = kwargs.get('supertrend_period', 10)
        self.supertrend_multiplier = kwargs.get('supertrend_multiplier', 3)
        self.rsi_period = kwargs.get('rsi_period', 14)
        self.rsi_buy_threshold = kwargs.get('rsi_buy_threshold', 50.0)
        self.rsi_sell_threshold = kwargs.get('rsi_sell_threshold', 70.0)
        self.quantity = kwargs.get('quantity', 1)

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.supertrend_period, self.rsi_period) + 5:
            return 'HOLD', 0.0, {}

        # Calculate indicators
        st_series, dir_series = calculate_supertrend(df, period=self.supertrend_period, multiplier=self.supertrend_multiplier)
        rsi_series = calculate_rsi(df['close'], period=self.rsi_period)

        df = df.copy()
        df['supertrend'] = st_series
        df['st_dir'] = dir_series
        df['rsi'] = rsi_series

        last = df.iloc[-1]

        # Entry Logic: SuperTrend UP (1) AND RSI > Threshold
        if last['st_dir'] == 1 and last['rsi'] > self.rsi_buy_threshold:
            return 'BUY', 1.0, {'reason': 'SuperTrend UP + RSI Momentum', 'price': last['close'], 'rsi': last['rsi'], 'st': last['supertrend']}

        # Exit Logic: SuperTrend DOWN (-1)
        if last['st_dir'] == -1:
             return 'SELL', 1.0, {'reason': 'SuperTrend Reversal (DOWN)', 'price': last['close'], 'rsi': last['rsi'], 'st': last['supertrend']}

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting strategy for {self.symbol}")

        while True:
            if not is_market_open():
                self.logger.info("Market is closed. Waiting...")
                time.sleep(60)
                continue

            try:
                # Determine exchange (NSE for stocks, NSE_INDEX for indices)
                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

                # Fetch historical data
                # We need enough data for indicators (e.g. 50-100 candles)
                start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
                end_date = datetime.now().strftime("%Y-%m-%d")

                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",
                    exchange=exchange,
                    start_date=start_date,
                    end_date=end_date
                )

                if df.empty or len(df) < 20:
                    self.logger.warning("Insufficient data. Waiting...")
                    time.sleep(60)
                    continue

                # Calculate indicators
                st_series, dir_series = calculate_supertrend(df, period=self.supertrend_period, multiplier=self.supertrend_multiplier)
                rsi_series = calculate_rsi(df['close'], period=self.rsi_period)

                last = df.iloc[-1]
                current_price = last['close']
                current_st_dir = dir_series.iloc[-1]
                current_rsi = rsi_series.iloc[-1]

                self.logger.info(f"Price: {current_price}, ST Dir: {current_st_dir}, RSI: {current_rsi:.2f}")

                # Position management
                if self.pm:
                    if self.pm.has_position():
                        # Exit logic
                        pnl = self.pm.get_pnl(current_price)

                        # Exit if SuperTrend flips to DOWN (-1)
                        if current_st_dir == -1:
                            self.logger.info(f"Exiting position (Trend Reversal). PnL: {pnl}")
                            # Close position (SELL if long)
                            if self.pm.position > 0:
                                self.pm.update_position(abs(self.pm.position), current_price, 'SELL')
                    else:
                        # Entry logic
                        # Buy if SuperTrend UP (1) AND RSI > Buy Threshold
                        if current_st_dir == 1 and current_rsi > self.rsi_buy_threshold:
                            qty = self.quantity
                            self.logger.info(f"Entry signal detected (ST UP + RSI > {self.rsi_buy_threshold}). Buying {qty} at {current_price}")
                            self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)  # Sleep between iterations

def run_strategy():
    parser = argparse.ArgumentParser(description='NSE SuperTrend RSI Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5000, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    # Custom parameters
    parser.add_argument('--supertrend_period', type=int, default=10, help='SuperTrend Period')
    parser.add_argument('--supertrend_multiplier', type=int, default=3, help='SuperTrend Multiplier')
    parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
    parser.add_argument('--rsi_buy_threshold', type=float, default=50.0, help='RSI Buy Threshold')
    parser.add_argument('--quantity', type=int, default=1, help='Quantity')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required")
        return

    strategy = NSESuperTrendRSIStrategy(
        args.symbol,
        api_key,
        args.port,
        supertrend_period=args.supertrend_period,
        supertrend_multiplier=args.supertrend_multiplier,
        rsi_period=args.rsi_period,
        rsi_buy_threshold=args.rsi_buy_threshold,
        quantity=args.quantity
    )
    strategy.run()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'supertrend_period': 10,
        'supertrend_multiplier': 3,
        'rsi_period': 14,
        'rsi_buy_threshold': 50.0,
        'quantity': 1
    }
    if params:
        strat_params.update(params)

    strat = NSESuperTrendRSIStrategy(
        symbol=symbol or "TEST",
        api_key="dummy",
        port=5000,
        **strat_params
    )

    # Disable logging for backtest
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.calculate_signal(df)

if __name__ == "__main__":
    run_strategy()
