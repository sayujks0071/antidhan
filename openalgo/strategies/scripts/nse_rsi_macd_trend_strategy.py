#!/usr/bin/env python3
"""
NSE RSI MACD Trend Strategy
Uses RSI and MACD for trend following.
Entry: MACD Line > Signal Line AND RSI > 50
Exit: MACD Line < Signal Line OR RSI < 40
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
    from trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi, calculate_macd
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi, calculate_macd
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi, calculate_macd
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            normalize_symbol = lambda s: s
            is_market_open = lambda: True
            calculate_rsi = lambda s: s
            calculate_macd = lambda s: (s, s, s)

class NSERSIMACDTrendStrategy:
    def __init__(self, symbol, api_key, port, **kwargs):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host) if APIClient else None

        # Setup Logger
        self.logger = logging.getLogger(f"NSE_{symbol}_Trend")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Avoid duplicate handlers if re-instantiated
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

        # Strategy parameters from kwargs
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.macd_fast = int(kwargs.get('macd_fast', 12))
        self.macd_slow = int(kwargs.get('macd_slow', 26))
        self.macd_signal = int(kwargs.get('macd_signal', 9))
        self.quantity = int(kwargs.get('quantity', 1))

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < 50:
            return 'HOLD', 0.0, {}

        # Calculate indicators
        try:
            df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
            macd_line, signal_line, hist = calculate_macd(
                df['close'],
                fast=self.macd_fast,
                slow=self.macd_slow,
                signal=self.macd_signal
            )
            df['macd_line'] = macd_line
            df['signal_line'] = signal_line
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            return 'HOLD', 0.0, {}

        last = df.iloc[-1]

        # Entry Logic: Bullish Crossover (MACD > Signal) AND RSI > 50

        is_bullish_macd = last['macd_line'] > last['signal_line']
        is_bullish_rsi = last['rsi'] > 50

        # Exit Logic: Bearish Crossover OR RSI < 40
        is_bearish_macd = last['macd_line'] < last['signal_line']
        is_weak_rsi = last['rsi'] < 40

        if is_bullish_macd and is_bullish_rsi:
             return 'BUY', 1.0, {
                 'reason': 'MACD Bullish + RSI > 50',
                 'price': last['close'],
                 'rsi': last['rsi'],
                 'macd': last['macd_line']
             }
        elif is_bearish_macd or is_weak_rsi:
            return 'SELL', 1.0, {
                'reason': 'MACD Bearish or RSI < 40',
                'price': last['close'],
                'rsi': last['rsi'],
                'macd': last['macd_line']
            }

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting NSE RSI MACD Trend Strategy for {self.symbol}")

        while True:
            if not is_market_open():
                self.logger.info("Market is closed. Waiting...")
                time.sleep(60)
                continue

            try:
                # Determine exchange
                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

                # Fetch historical data
                if self.client:
                    df = self.client.history(
                        symbol=self.symbol,
                        interval="5m",
                        exchange=exchange,
                        start_date=datetime.now().strftime("%Y-%m-%d"),
                        end_date=datetime.now().strftime("%Y-%m-%d")
                    )
                else:
                    self.logger.error("API Client not initialized")
                    time.sleep(60)
                    continue

                if df.empty or len(df) < 50:
                    self.logger.warning("Insufficient data. Waiting...")
                    time.sleep(60)
                    continue

                # Calculate indicators
                df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
                macd_line, signal_line, hist = calculate_macd(
                    df['close'],
                    fast=self.macd_fast,
                    slow=self.macd_slow,
                    signal=self.macd_signal
                )
                df['macd_line'] = macd_line
                df['signal_line'] = signal_line

                last = df.iloc[-1]
                current_price = last['close']

                # Conditions
                is_bullish_macd = last['macd_line'] > last['signal_line']
                is_bullish_rsi = last['rsi'] > 50

                is_bearish_macd = last['macd_line'] < last['signal_line']
                is_weak_rsi = last['rsi'] < 40

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    if is_bearish_macd or is_weak_rsi:
                        self.logger.info(f"Exit Signal. MACD Bearish: {is_bearish_macd}, RSI Weak: {is_weak_rsi}. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    if is_bullish_macd and is_bullish_rsi:
                        qty = self.quantity
                        self.logger.info(f"Entry Signal. MACD Bullish + RSI > 50. Buying {qty} at {current_price}")
                        self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error in strategy loop: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)  # Sleep between iterations

def run_strategy():
    parser = argparse.ArgumentParser(description='NSE RSI MACD Trend Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    # Strategy parameters
    parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
    parser.add_argument('--macd_fast', type=int, default=12, help='MACD Fast Period')
    parser.add_argument('--macd_slow', type=int, default=26, help='MACD Slow Period')
    parser.add_argument('--macd_signal', type=int, default=9, help='MACD Signal Period')
    parser.add_argument('--quantity', type=int, default=1, help='Trade Quantity')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required (pass --api_key or set OPENALGO_APIKEY env var)")
        return

    strategy = NSERSIMACDTrendStrategy(
        args.symbol,
        api_key,
        args.port,
        rsi_period=args.rsi_period,
        macd_fast=args.macd_fast,
        macd_slow=args.macd_slow,
        macd_signal=args.macd_signal,
        quantity=args.quantity
    )
    strategy.run()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'rsi_period': 14,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'quantity': 1
    }
    if params:
        strat_params.update(params)

    strat = NSERSIMACDTrendStrategy(
        symbol=symbol or "TEST",
        api_key="dummy",
        port=5001,
        **strat_params
    )

    # Suppress logging during backtest
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.calculate_signal(df)

if __name__ == "__main__":
    run_strategy()
