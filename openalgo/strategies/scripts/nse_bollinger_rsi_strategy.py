#!/usr/bin/env python3
"""
NSE Bollinger Bands + RSI Strategy
Entry: Close < Lower Band AND RSI < 30
Exit: Close > Upper Band OR RSI > 70
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
sys.path.insert(0, os.path.dirname(strategies_dir))

try:
    from trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi, calculate_bollinger_bands
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi, calculate_bollinger_bands
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_rsi, calculate_bollinger_bands
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            normalize_symbol = lambda s: s
            is_market_open = lambda: True
            calculate_rsi = lambda s, p: pd.Series(0, index=s.index)
            calculate_bollinger_bands = lambda s, w, n: (s, s, s)

class NSEBollingerRSIStrategy:
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
        self.rsi_period = kwargs.get('rsi_period', 14)
        self.bb_period = kwargs.get('bb_period', 20)
        self.bb_std = kwargs.get('bb_std', 2.0)
        self.risk_pct = kwargs.get('risk_pct', 2.0)

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.rsi_period, self.bb_period):
            return 'HOLD', 0.0, {}

        # Calculate indicators
        try:
            # Create a copy to avoid SettingWithCopyWarning if df is a slice
            df = df.copy()
            df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
            df['sma'], df['upper'], df['lower'] = calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
        except Exception as e:
            self.logger.error(f"Indicator calculation error: {e}")
            return 'HOLD', 0.0, {}

        last = df.iloc[-1]
        close = last['close']
        rsi = last['rsi']
        lower = last['lower']
        upper = last['upper']

        # Entry logic: Close < Lower Band AND RSI < 30 (Oversold)
        if close < lower and rsi < 30:
            return 'BUY', 1.0, {
                'reason': 'Oversold (RSI < 30) & Below Lower Band',
                'price': close,
                'rsi': rsi,
                'lower_band': lower
            }

        # Exit logic is handled in run(), but for backtesting signal generation, we might want to return SELL if exit condition met
        # Exit: Close > Upper Band OR RSI > 70 (Overbought)
        if close > upper or rsi > 70:
             return 'SELL', 1.0, {
                'reason': 'Overbought (RSI > 70) or Above Upper Band',
                'price': close,
                'rsi': rsi,
                'upper_band': upper
            }

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting strategy for {self.symbol}")

        while True:
            if not is_market_open():
                self.logger.info("Market is closed. Sleeping...")
                time.sleep(60)
                continue

            try:
                # Determine exchange (NSE for stocks, NSE_INDEX for indices)
                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

                # Fetch historical data
                now = datetime.now()
                start_date = (now - timedelta(days=5)).strftime("%Y-%m-%d") # Fetch enough data for indicators
                end_date = now.strftime("%Y-%m-%d")

                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",
                    exchange=exchange,
                    start_date=start_date,
                    end_date=end_date
                )

                if df.empty or len(df) < max(self.rsi_period, self.bb_period):
                    self.logger.warning("Insufficient data. Retrying...")
                    time.sleep(60)
                    continue

                # Calculate indicators & generate signal
                signal, signal_qty, metadata = self.calculate_signal(df)

                last = df.iloc[-1]
                current_price = last['close']

                # Position management
                if self.pm:
                    # Sync with real position if possible, but here rely on local state or PM logic
                    if self.pm.has_position():
                        # Exit logic
                        pnl = self.pm.get_pnl(current_price)

                        # Check exit condition from signal (SELL)
                        if signal == 'SELL':
                            self.logger.info(f"Exit signal detected: {metadata}. PnL: {pnl:.2f}")
                            self.pm.update_position(abs(self.pm.position), current_price, 'SELL')

                    else:
                        # Entry logic
                        if signal == 'BUY':
                            # Adaptive Quantity
                            qty = self.pm.calculate_adaptive_quantity(100000, self.risk_pct, 1.0, current_price) # Placeholder capital
                            qty = max(1, qty) # Ensure at least 1

                            self.logger.info(f"Entry signal detected: {metadata}. Buying {qty} at {current_price}")
                            self.pm.update_position(qty, current_price, 'BUY')

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
    parser.add_argument('--bb_period', type=int, default=20, help='Bollinger Band Period')
    parser.add_argument('--bb_std', type=float, default=2.0, help='Bollinger Band Std Dev')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required")
        return

    strategy = NSEBollingerRSIStrategy(
        args.symbol,
        api_key,
        args.port,
        rsi_period=args.rsi_period,
        bb_period=args.bb_period,
        bb_std=args.bb_std
    )
    strategy.run()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0
    }
    if params:
        strat_params.update(params)

    strat = NSEBollingerRSIStrategy(
        symbol=symbol or "TEST",
        api_key="dummy",
        port=5001,
        **strat_params
    )

    # Suppress logging for backtests
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.calculate_signal(df)

if __name__ == "__main__":
    run_strategy()
