#!/usr/bin/env python3
"""
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis, Enhanced Sector RSI Filter, and Dynamic Risk.
Refactored to use BaseStrategy and strategy_preamble.
"""
import strategy_preamble
from base_strategy import BaseStrategy
import pandas as pd

class SuperTrendVWAPStrategy(BaseStrategy):
    def setup(self):
        """Initialize strategy parameters."""
        if self.symbol:
            self.name = f"VWAP_{self.symbol}"

        # Strategy Parameters
        self.threshold = getattr(self, "threshold", 150)
        self.stop_pct = getattr(self, "stop_pct", 1.8)
        self.adx_threshold = getattr(self, "adx_threshold", 20)
        self.adx_period = getattr(self, "adx_period", 14)

        # Risk Parameters
        self.ATR_SL_MULTIPLIER = getattr(self, "ATR_SL_MULTIPLIER", 3.0)

        # Declarative Indicators
        self.indicators = {
            'atr': 14,
            'adx': self.adx_period,
            'ema': 200 # For trend check
        }

        # State
        self.trailing_stop = 0.0

    def calculate_indicators(self, df):
        """Override to add VWAP."""
        df = super().calculate_indicators(df)
        try:
            df = self.calculate_intraday_vwap(df)
        except Exception as e:
            self.logger.error(f"VWAP calc failed: {e}")
        return df

    def generate_signal(self, df):
        """
        Generate signal and manage trailing stop.
        Returns: ("BUY"/"SELL"/"EXIT"/"HOLD", qty, details)
        """
        if df.empty or 'vwap' not in df.columns:
            return "HOLD"

        last = df.iloc[-1]
        close = last['close']
        vwap = last['vwap']
        atr = last['atr']

        # Volume Profile
        poc_price, poc_vol = self.analyze_volume_profile(df)

        # VIX
        vix = self.get_vix()
        size_multiplier, dev_threshold = self.calculate_vix_volatility_multiplier(vix)

        # Position Management & Trailing Stop
        if self.pm and self.pm.has_position():
            sl_mult = self.ATR_SL_MULTIPLIER

            # Initialize or Update Trailing Stop
            if self.trailing_stop == 0:
                self.trailing_stop = close - (sl_mult * atr)

            new_stop = close - (sl_mult * atr)
            if new_stop > self.trailing_stop:
                self.trailing_stop = new_stop
                self.logger.info(f"Trailing Stop Updated: {self.trailing_stop:.2f}")

            # Check Exit Conditions
            if close < self.trailing_stop:
                self.logger.info(f"Signal: EXIT (Trailing Stop Hit at {close:.2f})")
                self.trailing_stop = 0.0
                return "EXIT"
            elif close < vwap:
                self.logger.info(f"Signal: EXIT (Price < VWAP at {close:.2f})")
                self.trailing_stop = 0.0
                return "EXIT"

            return "HOLD"

        else:
            # Entry Logic
            self.trailing_stop = 0.0 # Reset

            # Indicators
            is_above_vwap = close > vwap

            vol_mean = df['volume'].rolling(20).mean().iloc[-1]
            vol_std = df['volume'].rolling(20).std().iloc[-1]
            dynamic_threshold = vol_mean + (1.5 * vol_std)
            is_volume_spike = last['volume'] > dynamic_threshold

            is_above_poc = close > poc_price

            # vwap_dev might be calculated in calculate_intraday_vwap
            vwap_dev = last.get('vwap_dev', 0)
            is_not_overextended = abs(vwap_dev) < dev_threshold

            # Sector Check
            sector_bullish = self.check_sector_correlation(self.sector or "NIFTY BANK")

            if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and sector_bullish:
                # Adaptive Sizing
                base_qty = self.get_adaptive_quantity(close, risk_pct=1.0, capital=500000)
                adj_qty = max(1, int(base_qty * size_multiplier))

                self.logger.info(f"Signal: BUY. Price: {close:.2f}, POC: {poc_price:.2f}, Qty: {adj_qty} (VIX: {vix})")
                return "BUY", adj_qty

        return "HOLD"

    def get_signal(self, df):
        """Backtesting interface."""
        res = self.generate_signal(df)
        if isinstance(res, tuple):
            return res[0], res[1], {}
        elif isinstance(res, str):
             return res, self.quantity, {}
        return "HOLD", 0, {}

if __name__ == "__main__":
    SuperTrendVWAPStrategy.cli()
