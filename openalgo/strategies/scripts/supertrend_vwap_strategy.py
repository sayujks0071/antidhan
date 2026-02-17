#!/usr/bin/env python3
"""
[Optimization 2026-01-31] Changes: threshold: 155 -> 150 (Lowered due to Rejection 100.0%)
[Improvement 2026-02-01] Found 'threshold' parameter was unused. Relaxing dev_threshold to improve participation.
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis, Enhanced Sector RSI Filter, and Dynamic Risk.
"""
import os
import sys
import logging
import pandas as pd

# Add repo root to path to allow imports (if running as script)
try:
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol, calculate_vix_volatility_multiplier
except ImportError:
    # Try setting path to find utils
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol, calculate_vix_volatility_multiplier

class SuperTrendVWAPStrategy(BaseStrategy):
    def setup(self):
        if self.symbol:
            self.name = f"VWAP_{self.symbol}"

        # Logic for sector benchmark (BaseStrategy handles --sector -> self.sector)
        self.sector_benchmark = self.sector if self.sector else 'NIFTY BANK'

        # Optimization Parameters
        self.threshold = getattr(self, "threshold", 150)
        self.stop_pct = getattr(self, "stop_pct", 1.8)
        self.adx_threshold = getattr(self, "adx_threshold", 20)
        self.adx_period = getattr(self, "adx_period", 14)

        # State
        self.trailing_stop = 0.0
        self.atr = 0.0

    def cycle(self):
        """
        Main Strategy Logic Execution Cycle
        """
        exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() or "VIX" in self.symbol.upper() else "NSE"

        # Increased lookback to 30 days to handle weekends/data gaps better
        df = self.fetch_history(days=30, exchange=exchange)
        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}: {len(df)} rows. Need at least 50.")
            return

        # Pre-process
        try:
            df = self.calculate_intraday_vwap(df)
            if 'vwap' not in df.columns or 'vwap_dev' not in df.columns:
                self.logger.error("VWAP calculation failed - missing required columns")
                return
        except Exception as e:
            self.logger.error(f"VWAP calc failed: {e}", exc_info=True)
            return

        self.atr = self.calculate_atr(df)
        last = df.iloc[-1]

        # Adaptive Sizing (Monthly ATR)
        base_qty = self.get_adaptive_quantity(last['close'], risk_pct=1.0, capital=500000)

        # Volume Profile
        poc_price, poc_vol = self.analyze_volume_profile(df)

        # Dynamic Deviation based on VIX
        vix = self.get_vix()
        size_multiplier, dev_threshold = calculate_vix_volatility_multiplier(vix)

        # Indicators
        is_above_vwap = last['close'] > last['vwap']

        vol_mean = df['volume'].rolling(20).mean().iloc[-1]
        vol_std = df['volume'].rolling(20).std().iloc[-1]
        dynamic_threshold = vol_mean + (1.5 * vol_std)
        is_volume_spike = last['volume'] > dynamic_threshold

        is_above_poc = last['close'] > poc_price
        is_not_overextended = abs(last['vwap_dev']) < dev_threshold

        if self.pm and self.pm.has_position():
            # Manage Position
            sl_mult = getattr(self, 'ATR_SL_MULTIPLIER', 3.0)

            if self.trailing_stop == 0:
                self.trailing_stop = last['close'] - (sl_mult * self.atr)

            new_stop = last['close'] - (sl_mult * self.atr)
            if new_stop > self.trailing_stop:
                self.trailing_stop = new_stop
                self.logger.info(f"Trailing Stop Updated: {self.trailing_stop:.2f}")

            if last['close'] < self.trailing_stop:
                self.logger.info(f"Trailing Stop Hit at {last['close']:.2f}")
                self.execute_trade('SELL', self.quantity, last['close'])
                self.trailing_stop = 0.0
            elif last['close'] < last['vwap']:
                self.logger.info(f"Price crossed below VWAP at {last['close']:.2f}. Exiting.")
                self.execute_trade('SELL', self.quantity, last['close'])
                self.trailing_stop = 0.0
        else:
            # Entry Logic
            # Use self.sector (managed by BaseStrategy) instead of self.sector_benchmark
            # If self.sector is None, check_sector_correlation handles it (defaults to NIFTY BANK or passed value)
            # BaseStrategy sets self.sector from --sector argument
            sector_bullish = self.check_sector_correlation(self.sector or "NIFTY BANK")

            if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and sector_bullish:
                # Use base_qty calculated from adaptive sizing
                adj_qty = int(base_qty * size_multiplier)
                if adj_qty < 1: adj_qty = 1
                self.logger.info(f"VWAP Crossover Buy. Price: {last['close']:.2f}, POC: {poc_price:.2f}, Vol: {last['volume']}, Sector: Bullish, Dev: {last['vwap_dev']:.4f}, Qty: {adj_qty} (VIX: {vix})")

                self.execute_trade('BUY', adj_qty, last['close'])
                sl_mult = getattr(self, 'ATR_SL_MULTIPLIER', 3.0)
                self.trailing_stop = last['close'] - (sl_mult * self.atr)


    def generate_signal(self, df):
        """
        Generate signal for backtesting (Legacy Support)
        """
        if df.empty: return 'HOLD', {}, {}
        df = df.sort_index()

        try:
            df = self.calculate_intraday_vwap(df)
        except:
            return 'HOLD', {}, {}

        self.atr = self.calculate_atr(df)

        poc_price, poc_vol = self.analyze_volume_profile(df)

        # Mock VIX for backtest if not available
        vix = 15.0
        # Relaxed dev_threshold for backtest as well
        dev_threshold = 0.03

        # Logic
        last = df.iloc[-1]
        df['ema200'] = self.calculate_ema(df['close'], period=200)
        last = df.iloc[-1]
        is_uptrend = True
        if not pd.isna(last['ema200']):
            is_uptrend = last['close'] > last['ema200']

        is_above_vwap = last['close'] > last['vwap']

        vol_mean = df['volume'].rolling(20).mean().iloc[-1]
        vol_std = df['volume'].rolling(20).std().iloc[-1]
        dynamic_threshold = vol_mean + (1.5 * vol_std)
        is_volume_spike = last['volume'] > dynamic_threshold

        is_above_poc = last['close'] > poc_price
        is_not_overextended = abs(last['vwap_dev']) < dev_threshold

        adx = self.calculate_adx(df, period=self.adx_period)
        is_strong_trend = adx > self.adx_threshold

        sector_bullish = True # Assumed for backtest

        details = {
            'close': last['close'],
            'vwap': last['vwap'],
            'atr': self.atr,
            'poc': poc_price,
            'adx': adx
        }

        if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and sector_bullish and is_strong_trend and is_uptrend:
            return 'BUY', 1.0, details

        return 'HOLD', 0.0, details

# Module level wrapper for SimpleBacktestEngine
def generate_signal(df, client=None, symbol=None, params=None):
    # Pass params as kwargs to __init__ which BaseStrategy handles
    kwargs = params or {}
    strat = SuperTrendVWAPStrategy(symbol=symbol or "TEST", quantity=1, api_key="test", host="test", client=client, **kwargs)
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    setattr(strat, 'BREAKEVEN_TRIGGER_R', 1.5)
    setattr(strat, 'ATR_SL_MULTIPLIER', 3.0)
    setattr(strat, 'ATR_TP_MULTIPLIER', 5.0)

    action, score, details = strat.generate_signal(df)
    return action, score, details

if __name__ == "__main__":
    SuperTrendVWAPStrategy.cli()
