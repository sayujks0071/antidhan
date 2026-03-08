#!/usr/bin/env python3
"""
MCX Copper Trend Strategy
Trend-following logic with proper API integration.
"""
import logging
from strategy_preamble import BaseStrategy

class MCXCopperTrendStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        kwargs.setdefault('interval', '15m')
        kwargs.setdefault('exchange', 'MCX')
        super().__init__(**kwargs)

        self.params = {
            "period_rsi": 14,
            "period_atr": 14,
            "bb_window": 20,
            "bb_std": 2.0,
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

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--bb_window", type=int, default=20, help="Bollinger Bands Window")
        parser.add_argument("--bb_std", type=float, default=2.0, help="Bollinger Bands Std Dev")

    def cycle(self):
        df = self.fetch_history(days=5, interval=self.interval)
        if df.empty or len(df) < max(self.params["bb_window"], self.params["period_rsi"]) + 5:
            self.logger.warning(f"Insufficient data for {self.symbol}.")
            return

        df = self.calculate_indicators(df)
        current = df.iloc[-1]
        prev = df.iloc[-2]
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

        bullish_bb_breakout = (current["close"] > current["bb_upper"]) and (prev["close"] <= prev["bb_upper"])
        bearish_bb_breakout = (current["close"] < current["bb_lower"]) and (prev["close"] >= prev["bb_lower"])
        momentum_bullish = current["rsi"] > 55
        momentum_bearish = current["rsi"] < 45

        if not has_position:
            if bullish_bb_breakout and momentum_bullish:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}")
                self.buy(base_qty, current["close"])
            elif bearish_bb_breakout and momentum_bearish:
                self.logger.info(f"SELL SIGNAL: Price={current['close']}")
                self.sell(base_qty, current["close"])

        elif has_position:
            pos_qty = self.pm.position
            if pos_qty > 0 and (current["close"] < current["bb_sma"] or current["macd_line"] < current["macd_signal"]):
                self.logger.info(f"EXIT LONG: Trend Reversal. Price={current['close']}")
                self.sell(abs(pos_qty), current["close"])
            elif pos_qty < 0 and (current["close"] > current["bb_sma"] or current["macd_line"] > current["macd_signal"]):
                self.logger.info(f"EXIT SHORT: Trend Reversal. Price={current['close']}")
                self.buy(abs(pos_qty), current["close"])

    def calculate_indicators(self, df):
        df = df.copy()
        bb_sma, bb_upper, bb_lower = self.calculate_bollinger_bands(df["close"], window=self.params["bb_window"], num_std=self.params["bb_std"])
        df["bb_sma"] = bb_sma
        df["bb_upper"] = bb_upper
        df["bb_lower"] = bb_lower

        macd_line, macd_signal, macd_hist = self.calculate_macd(df["close"], fast=self.params["macd_fast"], slow=self.params["macd_slow"], signal=self.params["macd_signal"])
        df["macd_line"] = macd_line
        df["macd_signal"] = macd_signal

        df["rsi"] = self.calculate_rsi(df["close"], period=self.params["period_rsi"])
        df["atr"] = self.calculate_atr_series(df, period=self.params["period_atr"])
        return df

    def get_signal(self, df):
        if df.empty: return 'HOLD', 0.0, {}
        df = self.calculate_indicators(df)
        current = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else current

        bullish_bb_breakout = (current["close"] > current["bb_upper"]) and (prev["close"] <= prev["bb_upper"])
        bearish_bb_breakout = (current["close"] < current["bb_lower"]) and (prev["close"] >= prev["bb_lower"])
        momentum_bullish = current["rsi"] > 55
        momentum_bearish = current["rsi"] < 45

        if bullish_bb_breakout and momentum_bullish:
            return "BUY", 1.0, {"rsi": current["rsi"], "bb_upper": current["bb_upper"]}
        elif bearish_bb_breakout and momentum_bearish:
            return "SELL", 1.0, {"rsi": current["rsi"], "bb_lower": current["bb_lower"]}

        return "HOLD", 0.0, {}

generate_signal = MCXCopperTrendStrategy.backtest_signal

if __name__ == "__main__":
    MCXCopperTrendStrategy.cli()
