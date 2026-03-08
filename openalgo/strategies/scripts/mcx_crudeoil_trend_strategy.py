#!/usr/bin/env python3
"""
MCX CrudeOil Trend Strategy
Trend-following strategy for Crude Oil using EMA crossover, RSI filter, and Dynamic Sizing.
"""
import logging
from strategy_preamble import BaseStrategy

class MCXCrudeOilTrendStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        kwargs.setdefault('interval', '15m')
        kwargs.setdefault('exchange', 'MCX')
        super().__init__(**kwargs)

        self.params = {
            "period_rsi": 14,
            "period_atr": 14,
            "ema_fast": 20,
            "ema_slow": 50,
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
        parser.add_argument("--ema_fast", type=int, default=20, help="Fast EMA Period")
        parser.add_argument("--ema_slow", type=int, default=50, help="Slow EMA Period")

    def cycle(self):
        df = self.fetch_history(days=5, interval=self.interval)
        if df.empty or len(df) < max(self.params["ema_slow"], self.params["period_rsi"]) + 5:
            self.logger.warning(f"Insufficient data for {self.symbol}.")
            return

        df = self.calculate_indicators(df)
        current = df.iloc[-1]
        prev = df.iloc[-2]
        has_position = self.pm.has_position() if self.pm else False

        seasonality_ok = self.params.get("seasonality_score", 50) > 40
        global_alignment_ok = self.params.get("global_alignment_score", 50) >= 40
        usd_vol_high = self.params.get("usd_inr_volatility", 0) > 1.0

        base_qty = self.get_adaptive_quantity(current['close'])
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(round(base_qty * 0.7)))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        bullish_crossover = (current["ema_fast"] > current["ema_slow"]) and (prev["ema_fast"] <= prev["ema_slow"])
        bearish_crossover = (current["ema_fast"] < current["ema_slow"]) and (prev["ema_fast"] >= prev["ema_slow"])

        momentum_bullish = current["rsi"] > 50
        momentum_bearish = current["rsi"] < 50

        if not has_position:
            if bullish_crossover and momentum_bullish:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}")
                self.buy(base_qty, current["close"])
            elif bearish_crossover and momentum_bearish:
                self.logger.info(f"SELL SIGNAL: Price={current['close']}")
                self.sell(base_qty, current["close"])

        elif has_position:
            pos_qty = self.pm.position
            if pos_qty > 0 and bearish_crossover:
                self.logger.info(f"EXIT LONG: Trend Reversal. Price={current['close']}")
                self.sell(abs(pos_qty), current["close"])
            elif pos_qty < 0 and bullish_crossover:
                self.logger.info(f"EXIT SHORT: Trend Reversal. Price={current['close']}")
                self.buy(abs(pos_qty), current["close"])

    def calculate_indicators(self, df):
        df = df.copy()
        df["ema_fast"] = self.calculate_ema(df["close"], period=self.params["ema_fast"])
        df["ema_slow"] = self.calculate_ema(df["close"], period=self.params["ema_slow"])
        df["rsi"] = self.calculate_rsi(df["close"], period=self.params["period_rsi"])
        df["atr"] = self.calculate_atr_series(df, period=self.params["period_atr"])
        return df

    def get_signal(self, df):
        if df.empty: return 'HOLD', 0.0, {}
        df = self.calculate_indicators(df)
        current = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else current

        bullish_crossover = (current["ema_fast"] > current["ema_slow"]) and (prev["ema_fast"] <= prev["ema_slow"])
        bearish_crossover = (current["ema_fast"] < current["ema_slow"]) and (prev["ema_fast"] >= prev["ema_slow"])
        momentum_bullish = current["rsi"] > 50
        momentum_bearish = current["rsi"] < 50

        if bullish_crossover and momentum_bullish:
            return "BUY", 1.0, {"rsi": current["rsi"], "ema_fast": current["ema_fast"]}
        elif bearish_crossover and momentum_bearish:
            return "SELL", 1.0, {"rsi": current["rsi"], "ema_fast": current["ema_fast"]}

        return "HOLD", 0.0, {}

generate_signal = MCXCrudeOilTrendStrategy.backtest_signal

if __name__ == "__main__":
    MCXCrudeOilTrendStrategy.cli()
