#!/usr/bin/env python3
"""
MCX Aluminium Trend Strategy
Uses MACD and RSI for trend following and momentum entries.
Enhanced with Multi-Factor inputs (USD/INR, Seasonality).
"""
import logging
import time
from datetime import datetime, timedelta
import pandas as pd

# Simplified Import using strategy_preamble
from strategy_preamble import BaseStrategy

class MCXAluminiumStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        kwargs.setdefault('interval', '15m')
        kwargs.setdefault('exchange', 'MCX')
        super().__init__(**kwargs)

        self.params = {
            "period_rsi": 14,
            "period_atr": 14,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "usd_inr_trend": getattr(self, "usd_inr_trend", "Neutral"),
            "usd_inr_volatility": getattr(self, "usd_inr_volatility", 0.0),
            "seasonality_score": getattr(self, "seasonality_score", 50),
            "global_alignment_score": getattr(self, "global_alignment_score", 50),
        }
        self.params.update(kwargs)

        self.logger.info(f"Initialized Strategy for {self.symbol}")
        self.logger.info(f"Filters: Seasonality={self.params.get('seasonality_score')}, USD_Vol={self.params.get('usd_inr_volatility')}")

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--macd_fast", type=int, default=12, help="MACD Fast Period")
        parser.add_argument("--macd_slow", type=int, default=26, help="MACD Slow Period")
        parser.add_argument("--macd_signal", type=int, default=9, help="MACD Signal Period")

    def cycle(self):
        df = self.fetch_history(days=5, interval=self.interval)
        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}.")
            return

        df = self.calculate_indicators(df)

        current = df.iloc[-1]
        has_position = self.pm.has_position() if self.pm else False

        seasonality_ok = self.params.get("seasonality_score", 50) > 40
        usd_vol_high = self.params.get("usd_inr_volatility", 0) > 1.0

        base_qty = self.get_adaptive_quantity(current['close'])
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(round(base_qty * 0.7)))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        bullish_crossover = (current["macd_line"] > current["macd_signal"])
        momentum_ok = (current["rsi"] > 50)
        entry_signal = bullish_crossover and momentum_ok

        if not has_position:
            if entry_signal:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, MACD={current['macd_line']:.2f}, Signal={current['macd_signal']:.2f}")
                self.buy(base_qty, current["close"])

        elif has_position:
            pos_qty = self.pm.position
            trend_reversal = (current["macd_line"] < current["macd_signal"])
            momentum_lost = (current["rsi"] < 40)

            if trend_reversal or momentum_lost:
                reason = "Trend Reversal" if trend_reversal else "Momentum Lost"
                self.logger.info(f"EXIT: {reason}. Price={current['close']}, RSI={current['rsi']:.2f}")
                if pos_qty > 0:
                    self.sell(abs(pos_qty), current["close"])
                else:
                    self.buy(abs(pos_qty), current["close"])

    def calculate_indicators(self, df):
        df = df.copy()
        macd_line, macd_signal, macd_hist = self.calculate_macd(df["close"], fast=self.params["macd_fast"], slow=self.params["macd_slow"], signal=self.params["macd_signal"])
        df["macd_line"] = macd_line
        df["macd_signal"] = macd_signal
        df["macd_hist"] = macd_hist

        df["rsi"] = self.calculate_rsi(df["close"], period=self.params["period_rsi"])
        df["atr"] = self.calculate_atr_series(df, period=self.params["period_atr"])
        return df

    def get_signal(self, df):
        if df.empty: return 'HOLD', 0.0, {}
        df = self.calculate_indicators(df)
        current = df.iloc[-1]

        bullish_crossover = (current["macd_line"] > current["macd_signal"])
        momentum_ok = (current["rsi"] > 50)

        if bullish_crossover and momentum_ok:
            return "BUY", 1.0, {"rsi": current["rsi"], "macd": current["macd_line"], "signal": current["macd_signal"]}

        return "HOLD", 0.0, {}

generate_signal = MCXAluminiumStrategy.backtest_signal

if __name__ == "__main__":
    MCXAluminiumStrategy.cli()
