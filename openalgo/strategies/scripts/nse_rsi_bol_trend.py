#!/usr/bin/env python3
"""
NSE RSI Bollinger Trend Strategy
Strategy for NSE Equities using RSI and Bollinger Bands for Mean Reversion.
Entry: Buy when Close < Lower Bollinger Band AND RSI < 30 (Oversold).
Exit: Sell when Close > Upper Bollinger Band OR RSI > 70 (Overbought).
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
project_root = os.path.dirname(strategies_dir)
sys.path.insert(0, utils_dir)
sys.path.insert(0, project_root)

try:
    from trading_utils import (
        APIClient,
        PositionManager,
        is_market_open,
        normalize_symbol,
        calculate_rsi,
        calculate_bollinger_bands,
                calculate_intraday_vwap,
                calculate_atr
    )
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import (
            APIClient,
            PositionManager,
            is_market_open,
            normalize_symbol,
            calculate_rsi,
            calculate_bollinger_bands,
            calculate_intraday_vwap
        )
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import (
                APIClient,
                PositionManager,
                is_market_open,
                normalize_symbol,
                calculate_rsi,
                calculate_bollinger_bands,
                    calculate_intraday_vwap,
                    calculate_atr
            )
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            normalize_symbol = lambda s: s
            is_market_open = lambda: True
            calculate_rsi = lambda s: s
            calculate_bollinger_bands = lambda s: (s, s, s)
            calculate_intraday_vwap = lambda df: df
            calculate_atr = lambda df, period=14: pd.Series([0]*len(df))

class NSERsiBolTrendStrategy:
    def __init__(self, symbol, api_key, port, **kwargs):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host) if APIClient else None

        # Setup Logger
        self.logger = logging.getLogger(f"NSE_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Clear existing handlers to avoid duplicates
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # Strategy parameters from kwargs
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.bb_period = int(kwargs.get('bb_period', 20))
        self.bb_std = float(kwargs.get('bb_std', 2.0))
        self.risk_pct = float(kwargs.get('risk_pct', 1.0))
        self.quantity = int(kwargs.get('quantity', 1))

        self.pm = PositionManager(symbol) if PositionManager else None

    def get_monthly_atr(self):
        """Fetch daily data and calculate ATR for adaptive sizing."""
        try:
            exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"
            df = self.client.history(
                symbol=self.symbol,
                interval="1d",
                exchange=exchange,
                start_date=(datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d"),
                end_date=datetime.now().strftime("%Y-%m-%d")
            )
            if df.empty or len(df) < 15:
                return 0.0

            atr = calculate_atr(df, period=14).iloc[-1]
            return atr
        except Exception as e:
            self.logger.error(f"Error calculating Monthly ATR: {e}")
            return 0.0

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.rsi_period, self.bb_period) + 5:
            return 'HOLD', 0.0, {}

        # Calculate indicators
        df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
        sma, upper, lower = calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
        df['bb_upper'] = upper
        df['bb_lower'] = lower

        last = df.iloc[-1]

        # Entry logic: Buy if Close < Lower Band AND RSI < 30
        if last['close'] < last['bb_lower'] and last['rsi'] < 30:
            return 'BUY', 1.0, {
                'reason': 'Oversold Reversion',
                'price': last['close'],
                'rsi': last['rsi'],
                'bb_lower': last['bb_lower']
            }

        # Exit logic: Sell if Close > Upper Band OR RSI > 70
        if last['close'] > last['bb_upper'] or last['rsi'] > 70:
             return 'SELL', 1.0, {
                'reason': 'Overbought Reversion',
                'price': last['close'],
                'rsi': last['rsi'],
                'bb_upper': last['bb_upper']
            }

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting NSE RSI Bollinger Trend Strategy for {self.symbol}")
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
                # We need enough data for indicators (e.g. 50 periods)
                # Using 5m interval
                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",
                    exchange=exchange,
                    start_date=datetime.now().strftime("%Y-%m-%d"), # Intraday for now
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < max(self.rsi_period, self.bb_period):
                    self.logger.info("Waiting for sufficient data...")
                    time.sleep(60)
                    continue

                # Calculate indicators
                df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
                sma, upper, lower = calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
                df['bb_upper'] = upper
                df['bb_lower'] = lower

                last = df.iloc[-1]
                current_price = last['close']
                current_rsi = last['rsi']
                current_lower = last['bb_lower']
                current_upper = last['bb_upper']

                self.logger.info(f"Price: {current_price}, RSI: {current_rsi:.2f}, BB: [{current_lower:.2f}, {current_upper:.2f}]")

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    # Exit if Close > Upper Band OR RSI > 70
                    if current_price > current_upper or current_rsi > 70:
                        self.logger.info(f"Exiting position. PnL: {pnl:.2f}. Reason: Target/Overbought")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    # Buy if Close < Lower Band AND RSI < 30
                    if current_price < current_lower and current_rsi < 30:
                        # Adaptive Sizing
                        monthly_atr = self.get_monthly_atr()
                        qty = self.quantity
                        if monthly_atr > 0 and self.pm:
                            qty = self.pm.calculate_adaptive_quantity_monthly_atr(500000, 1.0, monthly_atr, current_price)
                            self.logger.info(f"Adaptive Quantity: {qty} (Monthly ATR: {monthly_atr:.2f})")

                        self.logger.info(f"Entry signal detected (Oversold). Buying {qty} at {current_price}")
                        self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error in strategy loop: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)  # Sleep between iterations

def run_strategy():
    parser = argparse.ArgumentParser(description='NSE RSI Bollinger Trend Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol (e.g., RELIANCE)')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    # Custom parameters
    parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
    parser.add_argument('--bb_period', type=int, default=20, help='Bollinger Band Period')
    parser.add_argument('--bb_std', type=float, default=2.0, help='Bollinger Band Std Dev')
    parser.add_argument('--quantity', type=int, default=1, help='Trade Quantity')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required. Set OPENALGO_APIKEY env var or pass --api_key")
        return

    strategy = NSERsiBolTrendStrategy(
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
    """
    Generate signal for backtesting.
    """
    strat_params = {
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0
    }
    if params:
        strat_params.update(params)

    strat = NSERsiBolTrendStrategy(
        symbol=symbol or "TEST",
        api_key="dummy",
        port=5001,
        **strat_params
    )

    # Disable logging for backtest
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.calculate_signal(df)

if __name__ == "__main__":
    run_strategy()
