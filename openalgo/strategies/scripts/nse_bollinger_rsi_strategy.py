#!/usr/bin/env python3
"""
NSE Bollinger Bands + RSI Strategy
Entry: Close < Lower Band AND RSI < 30
Exit: Close > Upper Band OR RSI > 70
"""
import os
import sys
import logging
import pandas as pd
from datetime import datetime, timedelta

# Add repo root to path
try:
    from base_strategy import BaseStrategy
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy

class NSEBollingerRSIStrategy(BaseStrategy):
    def __init__(self, symbol, api_key=None, host=None, **kwargs):
        super().__init__(
            name=f"NSE_Bollinger_{symbol}",
            symbol=symbol,
            api_key=api_key,
            host=host,
            exchange="NSE",
            interval="5m",
            **kwargs
        )

        # Strategy parameters
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.bb_period = int(kwargs.get('bb_period', 20))
        self.bb_std = float(kwargs.get('bb_std', 2.0))
        self.risk_pct = float(kwargs.get('risk_pct', 2.0))

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
        parser.add_argument('--bb_period', type=int, default=20, help='Bollinger Band Period')
        parser.add_argument('--bb_std', type=float, default=2.0, help='Bollinger Band Std Dev')
        parser.add_argument('--risk_pct', type=float, default=2.0, help='Risk Percentage')
        # Legacy port argument support
        parser.add_argument("--port", type=int, help="API Port (Legacy support)")

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        if hasattr(args, 'rsi_period'): kwargs['rsi_period'] = args.rsi_period
        if hasattr(args, 'bb_period'): kwargs['bb_period'] = args.bb_period
        if hasattr(args, 'bb_std'): kwargs['bb_std'] = args.bb_std
        if hasattr(args, 'risk_pct'): kwargs['risk_pct'] = args.risk_pct

        # Support legacy --port arg by constructing host
        if hasattr(args, 'port') and args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"

        return kwargs

    def calculate_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.rsi_period, self.bb_period):
            return 'HOLD', 0.0, {}

        # Calculate indicators
        try:
            df = df.copy()
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            df['sma'], df['upper'], df['lower'] = self.calculate_bollinger_bands(df['close'], window=self.bb_period, num_std=self.bb_std)
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

        # Exit logic: Close > Upper Band OR RSI > 70 (Overbought)
        if close > upper or rsi > 70:
             return 'SELL', 1.0, {
                'reason': 'Overbought (RSI > 70) or Above Upper Band',
                'price': close,
                'rsi': rsi,
                'upper_band': upper
            }

        return 'HOLD', 0.0, {}

    def cycle(self):
        """Main execution cycle"""
        # Determine exchange (NSE for stocks, NSE_INDEX for indices)
        exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

        # Fetch historical data
        df = self.fetch_history(days=5, interval="5m", exchange=exchange)

        if df.empty or len(df) < max(self.rsi_period, self.bb_period):
            self.logger.warning("Insufficient data. Retrying...")
            return

        # Calculate indicators & generate signal
        signal, signal_qty, metadata = self.calculate_signal(df)

        last = df.iloc[-1]
        current_price = last['close']

        # Position management
        if self.pm:
            if self.pm.has_position():
                # Exit logic
                pnl = self.pm.get_pnl(current_price)

                # Check exit condition from signal (SELL)
                if signal == 'SELL':
                    self.logger.info(f"Exit signal detected: {metadata}. PnL: {pnl:.2f}")
                    self.execute_trade('SELL', abs(self.pm.position), current_price)
            else:
                # Entry logic
                if signal == 'BUY':
                    # Adaptive Quantity
                    # Use PM's adaptive quantity logic
                    # Using placeholder capital 100000 and 1.0 volatility (ATR placeholder if not available)

                    qty = self.pm.calculate_adaptive_quantity(100000, self.risk_pct, 1.0, current_price)
                    qty = max(1, qty)

                    self.logger.info(f"Entry signal detected: {metadata}. Buying {qty} at {current_price}")
                    self.execute_trade('BUY', qty, current_price)

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
        api_key="BACKTEST",
        host="http://127.0.0.1:5000",
        **strat_params
    )

    # Suppress logging for backtests
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.calculate_signal(df)

if __name__ == "__main__":
    NSEBollingerRSIStrategy.cli()
