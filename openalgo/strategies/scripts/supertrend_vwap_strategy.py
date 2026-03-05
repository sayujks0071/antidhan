#!/usr/bin/env python3
"""
[Optimization 2026-01-31] Changes: threshold: 155 -> 150 (Lowered due to Rejection 100.0%)
[Improvement 2026-02-01] Found 'threshold' parameter was unused. Relaxing dev_threshold to improve participation.
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis, Enhanced Sector RSI Filter, and Dynamic Risk.
"""
import logging
import pandas as pd

# Simplified Import using strategy_preamble
from strategy_preamble import BaseStrategy

class SuperTrendVWAPStrategy(BaseStrategy):
    # Declarative Parameters
    params = {
        'threshold': 150,
        'stop_pct': 1.8,
        'adx_threshold': 20,
        'adx_period': 14,
        'BREAKEVEN_TRIGGER_R': 1.5,
        'ATR_SL_MULTIPLIER': 3.0,
        'ATR_TP_MULTIPLIER': 5.0
    }

    def setup(self):
        if self.symbol:
            self.name = f"VWAP_{self.symbol}"

        # Logic for sector benchmark (BaseStrategy handles --sector -> self.sector)
        self.sector_benchmark = self.sector if self.sector else 'NIFTY BANK'

        # State
        self.trailing_stop = 0.0
        self.atr = 0.0

    def generate_signal(self, df):
        """
        Unified signal generation for both Live Execution (cycle) and Backtesting.
        """
        # Pre-process
        try:
            df = self.calculate_intraday_vwap(df)
            if 'vwap' not in df.columns or 'vwap_dev' not in df.columns:
                self.logger.error("VWAP calculation failed - missing required columns")
                return 'HOLD'
        except Exception as e:
            self.logger.error(f"VWAP calc failed: {e}", exc_info=True)
            return 'HOLD'

        self.atr = self.calculate_atr(df)
        last = df.iloc[-1]

        # Volume Profile
        poc_price, poc_vol = self.analyze_volume_profile(df)

        # Dynamic Deviation based on VIX
        vix = self.get_vix()
        # Mock VIX for backtest if unavailable (get_vix handles this gracefully usually, but just in case)
        if not vix: vix = 15.0

        size_multiplier, dev_threshold = self.calculate_vix_volatility_multiplier(vix)

        # Indicators
        is_above_vwap = last['close'] > last['vwap']

        vol_mean = df['volume'].rolling(20).mean().iloc[-1]
        vol_std = df['volume'].rolling(20).std().iloc[-1]
        dynamic_threshold = vol_mean + (1.5 * vol_std)
        is_volume_spike = last['volume'] > dynamic_threshold

        is_above_poc = last['close'] > poc_price
        is_not_overextended = abs(last['vwap_dev']) < dev_threshold

        # Manage Position (Exit Logic)
        if self.pm and self.pm.has_position():
            # Trailing Stop Logic would normally go here, but generate_signal is pure signal.
            # BaseStrategy manages basic exits, but complex trailing stops might need custom cycle logic.
            # For now, we'll return EXIT if stop conditions are met, though stateful trailing stop
            # is hard to express purely in generate_signal without passing state.

            # Re-implementing stateful trailing stop logic within generate_signal is tricky because
            # it's stateless per se.
            # However, for this refactor, we will stick to Entry logic in generate_signal
            # and let BaseStrategy handle standard exits or over-ride cycle if complex management is needed.

            # Check for basic exit conditions expressible here
            if last['close'] < last['vwap']:
                 return 'EXIT', 1.0, {'reason': 'Crossed below VWAP'}

            return 'HOLD'

        # Entry Logic
        # Sector check logic is heavy (fetches history), might want to skip for backtest speed
        # or mock it. BaseStrategy.check_sector_correlation handles it.
        sector_bullish = self.check_sector_correlation(self.sector_benchmark)

        details = {
            'close': last['close'],
            'vwap': last['vwap'],
            'atr': self.atr,
            'poc': poc_price,
            'dev': last['vwap_dev'],
            'vix': vix
        }

        if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and sector_bullish:
            # Adaptive Sizing
            base_qty = self.get_adaptive_quantity(last['close'], risk_pct=1.0, capital=500000)
            adj_qty = int(base_qty * size_multiplier)
            if adj_qty < 1: adj_qty = 1

            return 'BUY', adj_qty, details

        return 'HOLD', 0.0, details

    # Backtesting alias
    def get_signal(self, df):
        return self.generate_signal(df)

if __name__ == "__main__":
    SuperTrendVWAPStrategy.cli()
