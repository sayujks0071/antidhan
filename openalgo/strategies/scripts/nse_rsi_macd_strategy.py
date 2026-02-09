#!/usr/bin/env python3
"""
NSE RSI MACD Strategy
Trend following strategy using MACD crossover and RSI momentum confirmation.
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
# Add openalgo root to path to allow imports like 'from utils import httpx_client'
openalgo_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, openalgo_dir)

try:
    from trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            normalize_symbol = lambda s: s
            is_market_open = lambda: True
            calculate_rsi = lambda s, period=14: pd.Series([50]*len(s))

class NSERsiMacdStrategy:
    def __init__(self, symbol, api_key, port, **kwargs):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host) if APIClient else None

        # Setup Logger
        self.logger = logging.getLogger(f"NSE_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Avoid duplicate handlers
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

        # Strategy parameters
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.macd_fast = int(kwargs.get('macd_fast', 12))
        self.macd_slow = int(kwargs.get('macd_slow', 26))
        self.macd_signal = int(kwargs.get('macd_signal', 9))
        self.rsi_buy_threshold = float(kwargs.get('rsi_buy_threshold', 50.0))

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_macd(self, df):
        """Calculate MACD and Signal Line"""
        exp1 = df['close'].ewm(span=self.macd_fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=self.macd_slow, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=self.macd_signal, adjust=False).mean()
        return macd, signal_line

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < self.macd_slow + 5:
            return 'HOLD', 0.0, {}

        # Calculate indicators
        df = df.copy() # Ensure we don't modify original df in place if it matters
        df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
        df['macd'], df['signal_line'] = self.calculate_macd(df)

        last = df.iloc[-1]

        # Entry Logic: MACD > Signal (Trend Up) AND RSI > Threshold (Momentum)
        macd_buy = last['macd'] > last['signal_line']
        rsi_buy = last['rsi'] > self.rsi_buy_threshold

        # Exit Logic: MACD < Signal (Trend Down)
        macd_sell = last['macd'] < last['signal_line']

        if macd_buy and rsi_buy:
            return 'BUY', 1.0, {'reason': 'MACD_Bullish_RSI_Confirm', 'price': last['close'], 'rsi': last['rsi'], 'macd': last['macd']}

        elif macd_sell:
            return 'SELL', 1.0, {'reason': 'MACD_Bearish_Crossover', 'price': last['close'], 'rsi': last['rsi'], 'macd': last['macd']}

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting strategy for {self.symbol}")

        while True:
            if not is_market_open():
                self.logger.info("Market Closed. Sleeping...")
                time.sleep(60)
                continue

            try:
                # Determine exchange
                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

                # Fetch historical data
                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",
                    exchange=exchange,
                    start_date=datetime.now().strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < 30:
                    time.sleep(60)
                    continue

                # Calculate indicators
                df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
                df['macd'], df['signal_line'] = self.calculate_macd(df)

                last = df.iloc[-1]
                current_price = last['close']

                # Position management
                if self.pm and self.pm.has_position():
                    pnl = self.pm.get_pnl(current_price)

                    # Exit Condition: MACD Cross Under
                    if last['macd'] < last['signal_line']:
                        self.logger.info(f"Exit signal detected (MACD Bearish). PnL: {pnl:.2f}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')

                else:
                    # Entry Condition: MACD > Signal AND RSI > Threshold
                    if last['macd'] > last['signal_line'] and last['rsi'] > self.rsi_buy_threshold:
                        qty = 1 # Placeholder fixed quantity
                        self.logger.info(f"Entry signal detected (MACD Bullish). Buying {qty} at {current_price}")
                        self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description='NSE RSI MACD Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    # Custom parameters
    parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
    parser.add_argument('--macd_fast', type=int, default=12, help='MACD Fast Period')
    parser.add_argument('--macd_slow', type=int, default=26, help='MACD Slow Period')
    parser.add_argument('--macd_signal', type=int, default=9, help='MACD Signal Period')
    parser.add_argument('--rsi_buy_threshold', type=float, default=50.0, help='RSI Buy Threshold')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required (pass via --api_key or OPENALGO_APIKEY env var)")
        return

    strategy = NSERsiMacdStrategy(
        args.symbol,
        api_key,
        args.port,
        rsi_period=args.rsi_period,
        macd_fast=args.macd_fast,
        macd_slow=args.macd_slow,
        macd_signal=args.macd_signal,
        rsi_buy_threshold=args.rsi_buy_threshold
    )
    strategy.run()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'rsi_period': 14,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'rsi_buy_threshold': 50.0
    }
    if params:
        strat_params.update(params)

    strat = NSERsiMacdStrategy(
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
