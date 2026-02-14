#!/usr/bin/env python3
"""
NSE RSI MACD Strategy
Strategy for NSE Equities using RSI and MACD for Trend Following.
Entry: Buy when MACD Line crosses above Signal Line AND RSI > 50.
Exit: Sell when MACD Line crosses below Signal Line OR RSI > 70.
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

# robust import for core utilities
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
            print("Warning: openalgo package not found or core imports failed.")
            APIClient = None
            PositionManager = None
            normalize_symbol = lambda s: s
            is_market_open = lambda: True

# robust import or local implementation for indicators
try:
    from trading_utils import calculate_rsi, calculate_atr, calculate_macd
except ImportError:
    try:
        from utils.trading_utils import calculate_rsi, calculate_atr, calculate_macd
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import calculate_rsi, calculate_atr, calculate_macd
        except ImportError:
            # Fallback
            sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
            from strategies.utils.trading_utils import calculate_rsi, calculate_atr, calculate_macd

class NSERsiMacdStrategy:
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
        self.macd_fast = int(kwargs.get('macd_fast', 12))
        self.macd_slow = int(kwargs.get('macd_slow', 26))
        self.macd_signal = int(kwargs.get('macd_signal', 9))
        self.quantity = int(kwargs.get('quantity', 1))

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.macd_slow, self.rsi_period) + 5:
            return 'HOLD', 0.0, {}

        # Calculate indicators
        # Use try-except for calculate_rsi just in case implementation differs
        try:
            df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
        except TypeError:
             # Fallback if calculate_rsi implementation differs (e.g. no kwargs)
             df['rsi'] = calculate_rsi(df['close'])

        macd, signal_line, _ = calculate_macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
        df['macd'] = macd
        df['signal'] = signal_line

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Entry logic: Buy if MACD Crosses Above Signal AND RSI > 50
        # Check crossover: prev MACD <= prev Signal AND curr MACD > curr Signal
        bullish_crossover = (prev['macd'] <= prev['signal']) and (last['macd'] > last['signal'])

        if bullish_crossover and last['rsi'] > 50:
            return 'BUY', 1.0, {
                'reason': 'MACD Crossover + RSI Trend',
                'price': last['close'],
                'rsi': last['rsi'],
                'macd': last['macd']
            }

        # Exit logic: Sell if MACD Crosses Below Signal OR RSI > 70
        bearish_crossover = (prev['macd'] >= prev['signal']) and (last['macd'] < last['signal'])

        if bearish_crossover or last['rsi'] > 70:
             return 'SELL', 1.0, {
                'reason': 'MACD Reversal / Overbought',
                'price': last['close'],
                'rsi': last['rsi'],
                'macd': last['macd']
            }

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting NSE RSI MACD Strategy for {self.symbol}")
        self.logger.info(f"Params: RSI={self.rsi_period}, MACD=({self.macd_fast},{self.macd_slow},{self.macd_signal})")

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
                # Using 5m interval as default
                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",
                    exchange=exchange,
                    start_date=datetime.now().strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < max(self.macd_slow, self.rsi_period):
                    self.logger.info("Waiting for sufficient data...")
                    time.sleep(60)
                    continue

                # Calculate indicators
                try:
                    df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
                except TypeError:
                    df['rsi'] = calculate_rsi(df['close'])

                macd, signal_line, _ = calculate_macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
                df['macd'] = macd
                df['signal'] = signal_line

                last = df.iloc[-1]
                prev = df.iloc[-2]
                current_price = last['close']
                current_rsi = last['rsi']
                current_macd = last['macd']
                current_signal = last['signal']

                self.logger.info(f"Price: {current_price}, RSI: {current_rsi:.2f}, MACD: {current_macd:.2f}, Signal: {current_signal:.2f}")

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    # Exit if MACD Crosses Below Signal OR RSI > 70
                    bearish_crossover = (prev['macd'] >= prev['signal']) and (last['macd'] < last['signal'])

                    if bearish_crossover or current_rsi > 70:
                        reason = "MACD Cross Under" if bearish_crossover else "RSI Overbought"
                        self.logger.info(f"Exiting position. PnL: {pnl:.2f}. Reason: {reason}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    # Buy if MACD Crosses Above Signal AND RSI > 50
                    bullish_crossover = (prev['macd'] <= prev['signal']) and (last['macd'] > last['signal'])

                    if bullish_crossover and current_rsi > 50:
                        qty = self.quantity
                        # Adaptive Sizing check
                        if self.pm:
                             # Try to calculate adaptive quantity based on ATR if available, else use fixed
                             try:
                                 atr = calculate_atr(df).iloc[-1]
                                 if atr > 0:
                                     adaptive_qty = self.pm.calculate_risk_adjusted_quantity(500000, 1.0, atr, current_price)
                                     qty = max(1, adaptive_qty)
                                     self.logger.info(f"Adaptive Quantity: {qty} (ATR: {atr:.2f})")
                             except:
                                 pass

                        self.logger.info(f"Entry signal detected (Bullish Trend). Buying {qty} at {current_price}")
                        self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error in strategy loop: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)  # Sleep between iterations

def run_strategy():
    parser = argparse.ArgumentParser(description='NSE RSI MACD Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol (e.g., RELIANCE)')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    # Custom parameters
    parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
    parser.add_argument('--macd_fast', type=int, default=12, help='MACD Fast Period')
    parser.add_argument('--macd_slow', type=int, default=26, help='MACD Slow Period')
    parser.add_argument('--macd_signal', type=int, default=9, help='MACD Signal Period')
    parser.add_argument('--quantity', type=int, default=1, help='Trade Quantity')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required. Set OPENALGO_APIKEY env var or pass --api_key")
        return

    strategy = NSERsiMacdStrategy(
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
    """
    Generate signal for backtesting.
    """
    strat_params = {
        'rsi_period': 14,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9
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
