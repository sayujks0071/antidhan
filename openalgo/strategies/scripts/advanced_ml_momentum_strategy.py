#!/usr/bin/env python3
"""
Advanced ML Momentum Strategy
Momentum with relative strength and sector overlay.
"""
import os
import sys
import logging
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
try:
    from base_strategy import BaseStrategy
    from trading_utils import calculate_relative_strength
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy
    from trading_utils import calculate_relative_strength

class MLMomentumStrategy(BaseStrategy):
    def __init__(self, symbol, quantity, api_key=None, host=None,
                 threshold=0.01, stop_pct=1.0, sector_benchmark='NIFTY 50', vol_multiplier=0.5,
                 log_file=None, client=None, **kwargs):

        # Determine exchange based on symbol (similar to original logic)
        # However, BaseStrategy usually takes exchange as arg.
        # We'll use whatever is passed or default to NSE.
        exchange = kwargs.get('exchange', 'NSE')

        super().__init__(
            name=f"MLMomentum_{symbol}",
            symbol=symbol,
            quantity=quantity,
            interval="15m",
            exchange=exchange,
            api_key=api_key,
            host=host,
            log_file=log_file,
            client=client,
            sector_benchmark=sector_benchmark
        )
        self.roc_threshold = threshold
        self.stop_pct = stop_pct
        self.vol_multiplier = vol_multiplier

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--threshold', type=float, default=0.01, help='ROC Threshold')
        parser.add_argument('--stop_pct', type=float, default=1.0, help='Stop Loss %')
        parser.add_argument('--vol_multiplier', type=float, default=0.5, help='Volume Multiplier')

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        kwargs['threshold'] = args.threshold
        kwargs['stop_pct'] = args.stop_pct
        kwargs['vol_multiplier'] = args.vol_multiplier
        return kwargs

    def get_news_sentiment(self):
        # Simulated
        return 0.5 # Neutral to Positive

    def check_time_filter(self):
        """Avoid trading during low volume lunch hours (12:00 - 13:00)."""
        now = datetime.now()
        if 12 <= now.hour < 13:
            return False
        return True

    def cycle(self):
        # Time Filter
        if not self.check_time_filter():
            # If we have a position, we might hold, but no new entries
            if not (self.pm and self.pm.has_position()):
                self.logger.info("Lunch hour (12:00-13:00). Skipping new entries.")
                # We can't sleep 300 here because BaseStrategy cycles every 60s (or custom).
                # We just return.
                return

        try:
            # 1. Fetch Stock Data
            # Use NSE_INDEX for NIFTY index
            exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"
            df = self.fetch_history(days=30, exchange=exchange)

            if df.empty or len(df) < 50:
                self.logger.warning(f"Insufficient data for {self.symbol}: {len(df)}")
                return

            # 2. Fetch Index Data - Use NSE_INDEX for indices
            # NIFTY 50 is usually "NIFTY" in symbol map
            index_df = self.fetch_history(days=30, symbol="NIFTY", exchange="NSE_INDEX")

            # Fetch Sector for Sector Momentum Overlay
            sector_df = pd.DataFrame()
            if self.sector_benchmark:
                 # Usually sector benchmark is an index
                 sector_df = self.fetch_history(days=30, symbol=self.sector_benchmark, exchange="NSE_INDEX")

            # 3. Indicators
            df['roc'] = df['close'].pct_change(periods=10)

            # RSI
            # Use BaseStrategy wrapper
            df['rsi'] = self.calculate_rsi(df['close'], period=14, mode='series')

            # SMA for Trend
            df['sma50'] = df['close'].rolling(50).mean()

            last = df.iloc[-1]
            current_price = last['close']

            # Relative Strength vs NIFTY
            rs_excess = calculate_relative_strength(df, index_df)

            # Sector Momentum Overlay (Stock ROC vs Sector ROC)
            sector_outperformance = 0.0
            if not sector_df.empty:
                try:
                        sector_roc = sector_df['close'].pct_change(10).iloc[-1]
                        sector_outperformance = last['roc'] - sector_roc
                except: pass
            else:
                sector_outperformance = 0.001 # Assume positive if missing to not block

            # News Sentiment
            sentiment = self.get_news_sentiment()

            # Manage Position
            if self.pm and self.pm.has_position():
                pnl = self.pm.get_pnl(current_price)
                entry = self.pm.entry_price

                if (self.pm.position > 0 and current_price < entry * (1 - self.stop_pct/100)):
                    self.logger.info(f"Stop Loss Hit. PnL: {pnl}")
                    self.execute_trade('SELL', abs(self.pm.position), current_price)

                # Exit if Momentum Fades (RSI < 50)
                elif (self.pm.position > 0 and last['rsi'] < 50):
                        self.logger.info(f"Momentum Faded (RSI < 50). Exit. PnL: {pnl}")
                        self.execute_trade('SELL', abs(self.pm.position), current_price)

                return

            # Entry Logic
            # ROC > Threshold
            # RSI > 55
            # Relative Strength > 0 (Outperforming NIFTY)
            # Sector Outperformance > 0 (Outperforming Sector)
            # Price > SMA50 (Uptrend)
            # Sentiment > 0 (Not Negative)

            if (last['roc'] > self.roc_threshold and
                last['rsi'] > 55 and
                rs_excess > 0 and
                sector_outperformance > 0 and
                current_price > last['sma50'] and
                sentiment >= 0):

                # Volume check
                avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                if last['volume'] > avg_vol * self.vol_multiplier: # At least decent volume
                    self.logger.info(f"Strong Momentum Signal (ROC: {last['roc']:.3f}, RS: {rs_excess:.3f}). BUY.")
                    self.execute_trade('BUY', self.quantity, current_price)

        except Exception as e:
            self.logger.error(f"Error in ML Momentum strategy for {self.symbol}: {e}", exc_info=True)

    def calculate_signal(self, df):
        """Calculate signal for backtesting."""
        if df.empty or len(df) < 50:
            return 'HOLD', 0.0, {}

        # Indicators
        df['roc'] = df['close'].pct_change(periods=10)

        # RSI
        # Local calculation for backtest compatibility if not using self.calculate_rsi
        # But we can use self.calculate_rsi if we are instantiated
        # For pure DF operation without instance state:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs_val = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs_val))

        # SMA for Trend
        df['sma50'] = df['close'].rolling(50).mean()

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

    # Note: api_key and host are dummy here
    strat = MLMomentumStrategy(
        symbol=symbol or "TEST",
        quantity=1,
        api_key="dummy",
        host="http://test",
        threshold=float(strat_params.get('threshold', 0.01)),
        stop_pct=float(strat_params.get('stop_pct', 1.0)),
        sector_benchmark=strat_params.get('sector', 'NIFTY 50'),
        vol_multiplier=float(strat_params.get('vol_multiplier', 0.5)),
        client=client
    )

    # Silence logger
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.calculate_signal(df)

if __name__ == "__main__":
    MLMomentumStrategy.cli()
