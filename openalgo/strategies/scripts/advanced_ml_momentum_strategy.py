#!/usr/bin/env python3
"""
Advanced ML Momentum Strategy
Momentum with relative strength and sector overlay.
Refactored to use BaseStrategy.
"""
import os
import sys
import logging
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
try:
    from base_strategy import BaseStrategy
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy

class MLMomentumStrategy(BaseStrategy):
    def __init__(self, symbol, quantity=10, api_key=None, host=None, threshold=0.01, stop_pct=1.0, sector='NIFTY 50', vol_multiplier=0.5, **kwargs):
        super().__init__(
            name=f"MLMomentum_{symbol}",
            symbol=symbol,
            quantity=quantity,
            api_key=api_key,
            host=host,
            **kwargs
        )
        self.roc_threshold = threshold
        self.stop_pct = stop_pct
        self.sector = sector
        self.vol_multiplier = vol_multiplier

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--threshold', type=float, default=0.01, help='ROC Threshold')
        parser.add_argument('--stop_pct', type=float, default=1.0, help='Stop Loss %%')
        parser.add_argument('--vol_multiplier', type=float, default=0.5, help='Volume Multiplier')

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        if hasattr(args, 'threshold') and args.threshold: kwargs['threshold'] = args.threshold
        if hasattr(args, 'stop_pct') and args.stop_pct: kwargs['stop_pct'] = args.stop_pct
        if hasattr(args, 'vol_multiplier') and args.vol_multiplier: kwargs['vol_multiplier'] = args.vol_multiplier
        return kwargs

    def cycle(self):
        # Time Filter
        if self.is_lunch_break():
            if not (self.pm and self.pm.has_position()):
                self.logger.info("Lunch hour (12:00-13:00). Skipping new entries.")
                return

        # Fetch Data
        exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"
        df = self.fetch_history(days=30, interval="15m", exchange=exchange)

        if df.empty or len(df) < 50:
            return

        # Fetch Index Data
        index_df = self.fetch_history(days=30, symbol="NIFTY", interval="15m", exchange="NSE_INDEX")

        # Fetch Sector Data
        sector_df = self.fetch_history(days=30, symbol=self.sector, interval="15m", exchange="NSE_INDEX")

        # Indicators
        df['roc'] = self.calculate_roc(df['close'], period=10)
        df['rsi'] = self.calculate_rsi(df['close'])
        df['sma50'] = self.calculate_sma(df['close'], 50)

        last = df.iloc[-1]
        current_price = last['close']

        # Relative Strength vs NIFTY
        rs_excess = self.calculate_relative_strength(df, index_df)

        # Sector Momentum Overlay
        sector_outperformance = 0.0
        if not sector_df.empty:
            try:
                 sector_roc = self.calculate_roc(sector_df['close'], period=10).iloc[-1]
                 sector_outperformance = last['roc'] - sector_roc
            except: pass
        else:
            sector_outperformance = 0.001

        sentiment = self.get_news_sentiment()

        # Manage Position
        if self.pm and self.pm.has_position():
            pnl = self.pm.get_pnl(current_price)
            entry = self.pm.entry_price

            if (self.pm.position > 0 and current_price < entry * (1 - self.stop_pct/100)):
                self.logger.info(f"Stop Loss Hit. PnL: {pnl}")
                self.execute_trade('SELL', abs(self.pm.position), current_price)

            elif (self.pm.position > 0 and last['rsi'] < 50):
                 self.logger.info(f"Momentum Faded (RSI < 50). Exit. PnL: {pnl}")
                 self.execute_trade('SELL', abs(self.pm.position), current_price)

            return

        # Entry Logic
        if (last['roc'] > self.roc_threshold and
            last['rsi'] > 55 and
            rs_excess > 0 and
            sector_outperformance > 0 and
            current_price > last['sma50'] and
            sentiment >= 0):

            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > avg_vol * self.vol_multiplier:
                # Use Adaptive Sizing
                qty = self.get_adaptive_quantity(current_price)
                self.logger.info(f"Strong Momentum Signal (ROC: {last['roc']:.3f}, RS: {rs_excess:.3f}). BUY {qty}.")
                self.execute_trade('BUY', qty, current_price)

    def get_news_sentiment(self):
        # Simulated
        return 0.5

    def calculate_signal(self, df):
        """Calculate signal for backtesting."""
        if df.empty or len(df) < 50:
            return 'HOLD', 0.0, {}

        # Indicators
        df['roc'] = self.calculate_roc(df['close'], period=10)
        df['rsi'] = self.calculate_rsi(df['close'])
        df['sma50'] = self.calculate_sma(df['close'], 50)

        last = df.iloc[-1]
        current_price = last['close']

        rs_excess = 0.01 # Mock positive
        sector_outperformance = 0.01 # Mock positive
        sentiment = 0.5 # Mock positive

        # Entry Logic
        if (last['roc'] > self.roc_threshold and
            last['rsi'] > 55 and
            rs_excess > 0 and
            sector_outperformance > 0 and
            current_price > last['sma50'] and
            sentiment >= 0):

            # Volume check
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > avg_vol * self.vol_multiplier: # Stricter volume
                return 'BUY', 1.0, {'roc': last['roc'], 'rsi': last['rsi']}

        return 'HOLD', 0.0, {}

def run_strategy():
    MLMomentumStrategy.cli()

# Module level wrapper for SimpleBacktestEngine
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'threshold': 0.01,
        'stop_pct': 1.0,
        'sector': 'NIFTY 50',
        'vol_multiplier': 0.5
    }
    if params:
        strat_params.update(params)

    # Use BaseStrategy-compatible init
    strat = MLMomentumStrategy(
        symbol=symbol or "TEST",
        quantity=10, # Dummy
        api_key="dummy",
        host="http://127.0.0.1:5001",
        threshold=float(strat_params.get('threshold', 0.01)),
        stop_pct=float(strat_params.get('stop_pct', 1.0)),
        sector=strat_params.get('sector', 'NIFTY 50'),
        vol_multiplier=float(strat_params.get('vol_multiplier', 0.5))
    )

    # Silence logger
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.calculate_signal(df)

if __name__ == "__main__":
    run_strategy()
