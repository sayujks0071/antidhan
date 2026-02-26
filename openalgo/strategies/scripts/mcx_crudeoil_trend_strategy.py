#!/usr/bin/env python3
"""
MCX Crude Oil Trend Strategy
MCX Commodity trading strategy with EMA, RSI, and ATR analysis
Inherits from BaseStrategy.
"""
import os
import sys

# Add repo root to path
try:
    from strategy_preamble import BaseStrategy
except ImportError:
    from base_strategy import BaseStrategy

class MCXCrudeOilTrendStrategy(BaseStrategy):
    def setup(self):
        # Default Parameters
        self.period_rsi = getattr(self, "period_rsi", 14)
        self.period_atr = getattr(self, "period_atr", 14)
        self.period_ema = getattr(self, "period_ema", 20)

        # Multi-Factor Parameters
        self.usd_inr_volatility = getattr(self, "usd_inr_volatility", 0.0)
        self.seasonality_score = getattr(self, "seasonality_score", 50)

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--period_ema", type=int, default=20, help="EMA Period")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
        # Legacy
        parser.add_argument("--port", type=int, help="API Port (Legacy)")

    def calculate_indicators(self, df):
        """Calculate technical indicators"""
        df = df.copy()
        df["rsi"] = self.calculate_rsi(df["close"], self.period_rsi)
        df["atr"] = self.calculate_atr_series(df, self.period_atr)
        df["ema_fast"] = self.calculate_ema(df["close"], self.period_ema)
        return df

    def cycle(self):
        """Main execution logic"""
        # Fetch Data
        df = self.fetch_history(days=5, interval="15m", exchange="MCX")
        if df.empty or len(df) < 50:
            self.logger.warning("Insufficient data.")
            return

        df = self.calculate_indicators(df)
        self.check_signals(df)

    def check_signals(self, df):
        """Check entry and exit conditions"""
        current = df.iloc[-1]

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        base_qty = 1
        if self.pm:
            # Use Adaptive Sizing (Monthly ATR favored)
            try:
                base_qty = self.pm.calculate_adaptive_quantity(
                    capital=500000,
                    risk_per_trade_pct=1.0,
                    atr=current["atr"],
                    price=current["close"],
                    client=self.client,
                    exchange="MCX"
                )
                self.logger.info(f"Adaptive Quantity Calculated: {base_qty}")
            except Exception as e:
                self.logger.error(f"Adaptive sizing failed: {e}. Defaulting to 1.")
                base_qty = 1

        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7)) # Valid only if base > 1

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic
        # Buy: Close > EMA AND RSI > 50
        buy_signal = (current["close"] > current["ema_fast"]) and (current["rsi"] > 50)
        # Sell: Close < EMA AND RSI < 50
        sell_signal = (current["close"] < current["ema_fast"]) and (current["rsi"] < 50)

        if not has_position:
            if buy_signal:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.execute_trade("BUY", base_qty, current["close"])
            elif sell_signal:
                self.logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}")
                self.execute_trade("SELL", base_qty, current["close"])

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price
            atr_val = current["atr"]

            # Target/Stop
            target = 2.0 * atr_val
            stop = 1.0 * atr_val

            exit_signal = False
            reason = ""

            if pos_qty > 0: # Long
                if (current["close"] >= entry_price + target):
                    exit_signal = True
                    reason = "Target Hit"
                elif (current["close"] <= entry_price - stop):
                    exit_signal = True
                    reason = "Stop Loss Hit"
                elif (current["close"] < current["ema_fast"]): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"

                if exit_signal:
                    self.logger.info(f"EXIT LONG: {reason}")
                    self.execute_trade("SELL", abs(pos_qty), current["close"])

            elif pos_qty < 0: # Short
                if (current["close"] <= entry_price - target):
                    exit_signal = True
                    reason = "Target Hit"
                elif (current["close"] >= entry_price + stop):
                    exit_signal = True
                    reason = "Stop Loss Hit"
                elif (current["close"] > current["ema_fast"]): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"

                if exit_signal:
                    self.logger.info(f"EXIT SHORT: {reason}")
                    self.execute_trade("BUY", abs(pos_qty), current["close"])

    def get_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        df = self.calculate_indicators(df)
        current = df.iloc[-1]

        buy_signal = (current["close"] > current["ema_fast"]) and (current["rsi"] > 50)
        sell_signal = (current["close"] < current["ema_fast"]) and (current["rsi"] < 50)

        if buy_signal:
            return "BUY", 1.0, {"reason": "Trend Long"}
        elif sell_signal:
            return "SELL", 1.0, {"reason": "Trend Short"}

        return "HOLD", 0.0, {}

# Backtesting support
generate_signal = MCXCrudeOilTrendStrategy.backtest_signal

if __name__ == "__main__":
    MCXCrudeOilTrendStrategy.cli()
