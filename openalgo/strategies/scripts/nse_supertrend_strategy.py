#!/usr/bin/env python3
"""
NSE SuperTrend Strategy
Trend Following Strategy using SuperTrend and EMA 50 on NIFTY 50.
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
    from trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_supertrend, calculate_ema, calculate_atr
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_supertrend, calculate_ema, calculate_atr
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol, calculate_supertrend, calculate_ema, calculate_atr
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            normalize_symbol = lambda s: s
            is_market_open = lambda: True
            calculate_supertrend = lambda df, p, m: (pd.Series([0]*len(df)), pd.Series([1]*len(df)))
            calculate_ema = lambda s, p: s.ewm(span=p).mean()
            calculate_atr = lambda df, p: pd.Series([0]*len(df))

class NSESuperTrendStrategy:
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
        self.period = int(kwargs.get('period', 10))
        self.multiplier = float(kwargs.get('multiplier', 3.0))
        self.ema_period = int(kwargs.get('ema_period', 50))
        self.capital = float(kwargs.get('capital', 100000.0))
        self.risk_pct = float(kwargs.get('risk_pct', 1.0))

        self.pm = PositionManager(symbol) if PositionManager else None

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.period, self.ema_period):
            return 'HOLD', 0.0, {}

        # Calculate indicators
        supertrend, direction = calculate_supertrend(df, self.period, self.multiplier)
        ema = calculate_ema(df['close'], self.ema_period)

        last = df.iloc[-1]

        # Current state
        current_dir = direction.iloc[-1]
        current_ema = ema.iloc[-1]
        close = last['close']

        # Entry logic
        # Long: SuperTrend Up (1) AND Close > EMA
        if current_dir == 1 and close > current_ema:
             return 'BUY', 1.0, {'reason': 'SuperTrend Up + Above EMA', 'price': close}

        # Short: SuperTrend Down (-1) AND Close < EMA
        if current_dir == -1 and close < current_ema:
             return 'SELL', 1.0, {'reason': 'SuperTrend Down + Below EMA', 'price': close}

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
                # Determine exchange (NSE for stocks, NSE_INDEX for indices)
                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() or "BANKNIFTY" in self.symbol.upper() else "NSE"

                # Fetch historical data
                df = self.client.history(
                    symbol=self.symbol,
                    interval="5m",  # 5 minute interval
                    exchange=exchange,
                    start_date=datetime.now().strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < max(self.period, self.ema_period):
                    self.logger.warning("Insufficient data. waiting...")
                    time.sleep(60)
                    continue

                # Calculate indicators
                supertrend, direction = calculate_supertrend(df, self.period, self.multiplier)
                atr = calculate_atr(df)

                last = df.iloc[-1]
                current_price = last['close']
                current_dir = direction.iloc[-1]

                # Position management
                if self.pm and self.pm.has_position():
                    # Exit logic
                    pnl = self.pm.get_pnl(current_price)

                    exit_signal = False
                    if self.pm.position > 0: # Long
                        if current_dir == -1: # Trend became Down
                             exit_signal = True
                             self.logger.info(f"Exit Signal: SuperTrend Reversal (Long -> Short)")
                    elif self.pm.position < 0: # Short
                        if current_dir == 1: # Trend became Up
                             exit_signal = True
                             self.logger.info(f"Exit Signal: SuperTrend Reversal (Short -> Long)")

                    if exit_signal:
                        self.logger.info(f"Exiting position. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')
                else:
                    # Entry logic
                    signal, confidence, metadata = self.calculate_signal(df)

                    if signal == 'BUY':
                        # Calculate quantity based on ATR risk
                        qty = self.pm.calculate_adaptive_quantity(self.capital, self.risk_pct, atr.iloc[-1], current_price)
                        if qty > 0:
                            self.logger.info(f"Entry signal detected (BUY). Buying {qty} at {current_price}")
                            self.pm.update_position(qty, current_price, 'BUY')
                        else:
                            self.logger.warning("Signal BUY but calculated quantity is 0")

                    elif signal == 'SELL':
                        # Calculate quantity based on ATR risk
                        qty = self.pm.calculate_adaptive_quantity(self.capital, self.risk_pct, atr.iloc[-1], current_price)
                        if qty > 0:
                            self.logger.info(f"Entry signal detected (SELL). Selling {qty} at {current_price}")
                            self.pm.update_position(qty, current_price, 'SELL')
                        else:
                            self.logger.warning("Signal SELL but calculated quantity is 0")

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)  # Sleep between iterations

def run_strategy():
    parser = argparse.ArgumentParser(description='NSE SuperTrend Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    # Custom parameters
    parser.add_argument('--period', type=int, default=10, help='SuperTrend Period')
    parser.add_argument('--multiplier', type=float, default=3.0, help='SuperTrend Multiplier')
    parser.add_argument('--ema_period', type=int, default=50, help='EMA Period')
    parser.add_argument('--capital', type=float, default=100000.0, help='Capital for position sizing')
    parser.add_argument('--risk_pct', type=float, default=1.0, help='Risk Percentage per trade')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required")
        return

    strategy = NSESuperTrendStrategy(
        args.symbol,
        api_key,
        args.port,
        period=args.period,
        multiplier=args.multiplier,
        ema_period=args.ema_period,
        capital=args.capital,
        risk_pct=args.risk_pct
    )
    strategy.run()

# Backtesting support
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'period': 10,
        'multiplier': 3.0,
        'ema_period': 50
    }
    if params:
        strat_params.update(params)

    strat = NSESuperTrendStrategy(
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
