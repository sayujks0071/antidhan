#!/usr/bin/env python3
"""
NSE RSI Bollinger Trend Strategy
Strategy for NSE Equities using RSI and Bollinger Bands for Mean Reversion.
Entry: Buy when Close < Lower Bollinger Band AND RSI < 30 (Oversold).
Exit: Sell when Close > Upper Bollinger Band OR RSI > 70 (Overbought).
Refactored to inherit from BaseStrategy (Feb 2026).
"""
import os
import sys
import logging
import argparse

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')
if utils_dir not in sys.path:
    sys.path.insert(0, utils_dir)

try:
    from base_strategy import BaseStrategy
    from trading_utils import calculate_rsi, calculate_bollinger_bands, normalize_symbol
except ImportError:
    # Fallback if run from different context
    sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))
    from base_strategy import BaseStrategy
    from trading_utils import calculate_rsi, calculate_bollinger_bands, normalize_symbol

class NSERsiBolTrendStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        # Default interval to 5m if not provided
        if 'interval' not in kwargs:
            kwargs['interval'] = '5m'
        super().__init__(**kwargs)

        # Strategy parameters
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.bb_period = int(kwargs.get('bb_period', 20))
        self.bb_std = float(kwargs.get('bb_std', 2.0))
        # BaseStrategy uses self.risk from --risk argument (default 1.0)

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
        parser.add_argument('--bb_period', type=int, default=20, help='Bollinger Band Period')
        parser.add_argument('--bb_std', type=float, default=2.0, help='Bollinger Band Std Dev')
        parser.add_argument('--port', type=int, help='API Port (Override host)')

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        if hasattr(args, 'rsi_period'): kwargs['rsi_period'] = args.rsi_period
        if hasattr(args, 'bb_period'): kwargs['bb_period'] = args.bb_period
        if hasattr(args, 'bb_std'): kwargs['bb_std'] = args.bb_std

        # Handle port argument if present (legacy support)
        if hasattr(args, 'port') and args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"
        return kwargs

    def cycle(self):
        """
        Main logic execution per cycle.
        """
        try:
            # Determine exchange (NSE for stocks, NSE_INDEX for indices)
            exchange = self.exchange
            if self.symbol and "NIFTY" in self.symbol.upper() and "INDEX" not in exchange:
                 exchange = "NSE_INDEX"

            # Fetch historical data
            lookback = max(self.rsi_period, self.bb_period) + 10
            # 5m candles: 1 day is ~75 candles. 2 days ensures enough data.
            df = self.fetch_history(days=2, exchange=exchange)

            if df.empty or len(df) < lookback:
                self.logger.info(f"Waiting for sufficient data ({len(df)}/{lookback})...")
                return

            # Calculate indicators
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            # Use BaseStrategy method for consistency
            sma, upper, lower = self.calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
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
                    self.sell(abs(self.pm.position), current_price)
            else:
                # Entry logic
                # Buy if Close < Lower Band AND RSI < 30
                if current_price < current_lower and current_rsi < 30:
                    # Adaptive Sizing using BaseStrategy method
                    qty = self.get_adaptive_quantity(current_price, risk_pct=getattr(self, 'risk', 1.0))

                    self.logger.info(f"Entry signal detected (Oversold). Buying {qty} at {current_price}")
                    self.buy(qty, current_price)

        except Exception as e:
            self.logger.error(f"Error in strategy cycle: {e}", exc_info=True)

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.rsi_period, self.bb_period) + 5:
            return 'HOLD', 0.0, {}

        # Calculate indicators
        # Use copies or assign to avoid warnings if df is view
        df = df.copy()
        df['rsi'] = calculate_rsi(df['close'], period=self.rsi_period)
        sma, upper, lower = calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
        df['bb_upper'] = upper
        df['bb_lower'] = lower

        last = df.iloc[-1]

        # Entry logic: Buy if Close < Lower Band AND RSI < 30 (Oversold)
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

# Backtesting support function
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

    # Use BaseStrategy-compatible init
    strat = NSERsiBolTrendStrategy(
        symbol=symbol or "TEST",
        api_key="dummy",
        host="http://127.0.0.1:5001",
        **strat_params
    )

    # Inject client if provided
    if client:
        strat.client = client

    # Disable logging for backtest
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.calculate_signal(df)

def run_strategy():
    NSERsiBolTrendStrategy.cli()

if __name__ == "__main__":
    run_strategy()
