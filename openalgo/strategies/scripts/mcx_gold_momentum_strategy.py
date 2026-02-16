#!/usr/bin/env python3
"""
MCX Gold Momentum Strategy
MCX Commodity trading strategy with multi-factor analysis (RSI, EMA, ATR, Seasonality)
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
    utils_dir = os.path.join(strategies_dir, "utils")
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy

class MCXGoldMomentumStrategy(BaseStrategy):
    def __init__(self, symbol, api_key=None, host=None, **kwargs):
        super().__init__(
            name=f"MCX_Gold_{symbol}",
            symbol=symbol,
            api_key=api_key,
            host=host,
            exchange="MCX",
            interval="15m",
            **kwargs
        )

        # Strategy Parameters
        self.period_rsi = int(kwargs.get("period_rsi", 14))
        self.period_atr = int(kwargs.get("period_atr", 14))
        self.period_ema_fast = int(kwargs.get("period_ema_fast", 9))
        self.period_ema_slow = int(kwargs.get("period_ema_slow", 21))

        # Multi-Factor Parameters
        self.usd_inr_trend = kwargs.get("usd_inr_trend", "Neutral")
        self.usd_inr_volatility = float(kwargs.get("usd_inr_volatility", 0.0))
        self.seasonality_score = int(kwargs.get("seasonality_score", 50))
        self.global_alignment_score = int(kwargs.get("global_alignment_score", 50))

        self.data = pd.DataFrame()

        self.logger.info(f"Initialized Strategy for {symbol}")
        self.logger.info(f"Filters: Seasonality={self.seasonality_score}, USD_Vol={self.usd_inr_volatility}")

    @classmethod
    def add_arguments(cls, parser):
        # Strategy Parameters
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--period_ema_fast", type=int, default=9, help="Fast EMA Period")
        parser.add_argument("--period_ema_slow", type=int, default=21, help="Slow EMA Period")

        # Multi-Factor Arguments
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

        # Legacy port argument support
        parser.add_argument("--port", type=int, help="API Port (Legacy support)")

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        if hasattr(args, 'period_rsi'): kwargs['period_rsi'] = args.period_rsi
        if hasattr(args, 'period_atr'): kwargs['period_atr'] = args.period_atr
        if hasattr(args, 'period_ema_fast'): kwargs['period_ema_fast'] = args.period_ema_fast
        if hasattr(args, 'period_ema_slow'): kwargs['period_ema_slow'] = args.period_ema_slow
        if hasattr(args, 'usd_inr_trend'): kwargs['usd_inr_trend'] = args.usd_inr_trend
        if hasattr(args, 'usd_inr_volatility'): kwargs['usd_inr_volatility'] = args.usd_inr_volatility
        if hasattr(args, 'seasonality_score'): kwargs['seasonality_score'] = args.seasonality_score
        if hasattr(args, 'global_alignment_score'): kwargs['global_alignment_score'] = args.global_alignment_score

        # Support legacy --port arg by constructing host
        if hasattr(args, 'port') and args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"

        return kwargs

    def cycle(self):
        """Check entry and exit conditions"""
        # Fetch Data
        df = self.fetch_history(days=5, interval="15m")
        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}.")
            return

        if not self.check_new_candle(df):
            return

        self.data = df

        # Calculate Indicators locally
        df = df.copy()
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
        df["ema_fast"] = self.calculate_ema(df["close"], period=self.period_ema_fast)
        df["ema_slow"] = self.calculate_ema(df["close"], period=self.period_ema_slow)
        df["atr"] = self.calculate_atr_series(df, period=self.period_atr)

        current = df.iloc[-1]

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        base_qty = self.quantity
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic (BUY)
        # Condition: Fast EMA > Slow EMA AND RSI > 55
        entry_condition = (current["ema_fast"] > current["ema_slow"]) and (current["rsi"] > 55)

        if not has_position:
            if entry_condition:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, EMA_Fast={current['ema_fast']:.2f}, EMA_Slow={current['ema_slow']:.2f}")
                self.execute_trade("BUY", base_qty, current['close'])

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position

            # Condition: Fast EMA < Slow EMA (Trend Reversal) OR RSI < 40 (Momentum Lost)
            exit_condition = (current["ema_fast"] < current["ema_slow"]) or (current["rsi"] < 40)

            if exit_condition:
                self.logger.info(f"EXIT: Trend Faded. Price={current['close']}, RSI={current['rsi']:.2f}")
                self.execute_trade("SELL", abs(pos_qty), current['close'])

    def get_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        df = df.copy()
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
        df["ema_fast"] = self.calculate_ema(df["close"], period=self.period_ema_fast)
        df["ema_slow"] = self.calculate_ema(df["close"], period=self.period_ema_slow)

        current = df.iloc[-1]

        # Entry Condition
        entry_condition = (current["ema_fast"] > current["ema_slow"]) and (current["rsi"] > 55)

        if entry_condition:
            return "BUY", 1.0, {"reason": "signal_triggered", "rsi": current["rsi"], "ema_fast": current["ema_fast"], "ema_slow": current["ema_slow"]}

        return "HOLD", 0.0, {}

# Backtesting alias
generate_signal = MCXGoldMomentumStrategy.backtest_signal

if __name__ == "__main__":
    MCXGoldMomentumStrategy.cli()
