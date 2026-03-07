#!/usr/bin/env python3
"""
MCX Crude Oil Trend Strategy
MCX Commodity trading strategy with EMA, RSI, and ATR analysis
"""
import logging
import pandas as pd
from strategy_preamble import BaseStrategy

class MCXStrategy(BaseStrategy):
    def setup(self):
        """Initialize custom parameters and configure strategy."""
        if self.symbol:
            self.name = f"MCX_CrudeOil_Trend_{self.symbol}"

        # Ensure correct interval and exchange for MCX strategies
        self.interval = getattr(self, "interval", "15m")
        self.exchange = getattr(self, "exchange", "MCX")

        # Setup Strategy Custom Parameters
        self.period_rsi = getattr(self, "period_rsi", 14)
        self.period_atr = getattr(self, "period_atr", 14)
        self.period_ema = getattr(self, "period_ema", 20)
        self.usd_inr_trend = getattr(self, "usd_inr_trend", "Neutral")
        self.usd_inr_volatility = float(getattr(self, "usd_inr_volatility", 0.0))
        self.seasonality_score = int(getattr(self, "seasonality_score", 50))
        self.global_alignment_score = int(getattr(self, "global_alignment_score", 50))

        self.logger.info(f"Filters: Seasonality={self.seasonality_score}, USD_Vol={self.usd_inr_volatility}")

    @classmethod
    def add_arguments(cls, parser):
        """Add custom CLI arguments for multi-factor checks."""
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

    def cycle(self):
        """Main Strategy Logic Execution Cycle"""
        # Fetch and prepare data with automatic exchange detection
        df = self.fetch_and_prepare_data(days=5, min_rows=50)
        if df is None:
            return

        # Check for new candle
        if not self.check_new_candle(df):
            return

        # Calculate Indicators
        df["rsi"] = self.calculate_rsi(df["close"], self.period_rsi)
        df["atr"] = self.calculate_atr_series(df, self.period_atr)
        df["ema_fast"] = self.calculate_ema(df["close"], self.period_ema)

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
                base_qty = self.get_adaptive_quantity(
                    price=current["close"],
                    risk_pct=1.0,
                    capital=500000
                )
                self.logger.info(f"Adaptive Quantity Calculated: {base_qty}")
            except Exception as e:
                self.logger.error(f"Adaptive sizing failed: {e}. Defaulting to 1.")
                base_qty = 1

        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7))

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
                self.logger.info(f"EXIT: {reason}")
                self.execute_trade("SELL" if pos_qty > 0 else "BUY", abs(pos_qty), current["close"])

    def get_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        df = df.copy()

        df["rsi"] = self.calculate_rsi(df["close"], self.period_rsi)
        df["ema_fast"] = self.calculate_ema(df["close"], self.period_ema)

        if len(df) < 50:
            return "HOLD", 0.0, {}

        current = df.iloc[-1]

        buy_signal = (current["close"] > current["ema_fast"]) and (current["rsi"] > 50)
        sell_signal = (current["close"] < current["ema_fast"]) and (current["rsi"] < 50)

        details = {
            "close": current["close"],
            "rsi": current["rsi"],
            "ema_fast": current["ema_fast"],
        }

        if buy_signal:
            return "BUY", 1.0, {"reason": "Trend Long", **details}
        elif sell_signal:
            return "SELL", 1.0, {"reason": "Trend Short", **details}

        return "HOLD", 0.0, details

# Backtesting support using the wrapper in BaseStrategy
generate_signal = MCXStrategy.backtest_signal

if __name__ == "__main__":
    MCXStrategy.cli()
