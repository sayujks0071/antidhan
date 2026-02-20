#!/usr/bin/env python3
"""
MCX Gold Momentum Strategy
MCX Commodity trading strategy with multi-factor analysis (RSI, EMA, ATR, Seasonality).
Refactored to use BaseStrategy (Feb 2026).
"""
import logging
from strategy_preamble import BaseStrategy

class MCXStrategy(BaseStrategy):
    def setup(self):
        """Initialize strategy-specific parameters"""
        self.period_rsi = int(getattr(self, 'period_rsi', 14))
        self.period_atr = int(getattr(self, 'period_atr', 14))
        self.period_ema_fast = int(getattr(self, 'period_ema_fast', 9))
        self.period_ema_slow = int(getattr(self, 'period_ema_slow', 21))

        # Multi-factor filters
        self.usd_inr_trend = getattr(self, 'usd_inr_trend', "Neutral")
        self.usd_inr_volatility = float(getattr(self, 'usd_inr_volatility', 0.0))
        self.seasonality_score = int(getattr(self, 'seasonality_score', 50))
        self.global_alignment_score = int(getattr(self, 'global_alignment_score', 50))

        self.logger.info(f"Initialized Strategy for {self.symbol}")
        self.logger.info(f"Filters: Seasonality={self.seasonality_score}, USD_Vol={self.usd_inr_volatility}")

    @classmethod
    def add_arguments(cls, parser):
        # Multi-Factor Arguments
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

        # Strategy Parameters
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--period_ema_fast", type=int, default=9, help="Fast EMA Period")
        parser.add_argument("--period_ema_slow", type=int, default=21, help="Slow EMA Period")

        # Port argument for legacy compatibility
        parser.add_argument("--port", type=int, help="API Port (Override host)")

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        if hasattr(args, 'port') and args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"
        return kwargs

    def cycle(self):
        """Main execution cycle called every minute by BaseStrategy"""
        # MCX typically uses 15m, 5m, or 1h. Default here matches original script: 15m.
        # Ensure we fetch enough data for EMA(21) and RSI(14)
        df = self.fetch_history(days=5, interval="15m", exchange="MCX")

        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}.")
            return

        # Check for new candle
        if not self.check_new_candle(df):
            return

        # Calculate Indicators
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
        df["ema_fast"] = self.calculate_ema(df["close"], period=self.period_ema_fast)
        df["ema_slow"] = self.calculate_ema(df["close"], period=self.period_ema_slow)
        df["atr"] = self.calculate_atr_series(df, period=self.period_atr) # Use series version if needed, or scalar logic

        current = df.iloc[-1]

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        # Original script used base_qty=1 hardcoded, reduced by 30% if vol high.
        # Here we use self.quantity (from args)
        base_qty = self.quantity
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7))

        has_position = self.pm.has_position() if self.pm else False

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic (BUY)
        # Condition: Fast EMA > Slow EMA AND RSI > 55
        entry_condition = (current["ema_fast"] > current["ema_slow"]) and (current["rsi"] > 55)

        if not has_position:
            if entry_condition:
                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, EMA_Fast={current['ema_fast']:.2f}, EMA_Slow={current['ema_slow']:.2f}")
                self.buy(base_qty, current["close"])

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position

            # Condition: Fast EMA < Slow EMA (Trend Reversal) OR RSI < 40 (Momentum Lost)
            exit_condition = (current["ema_fast"] < current["ema_slow"]) or (current["rsi"] < 40)

            if exit_condition:
                self.logger.info(f"EXIT: Trend Faded. Price={current['close']}, RSI={current['rsi']:.2f}")
                self.sell(abs(pos_qty), current["close"])

    def get_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        # Calculate Indicators
        # Copy to avoid SettingWithCopyWarning
        df = df.copy()
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
        df["ema_fast"] = self.calculate_ema(df["close"], period=self.period_ema_fast)
        df["ema_slow"] = self.calculate_ema(df["close"], period=self.period_ema_slow)

        current = df.iloc[-1]

        # Entry Condition
        entry_condition = (current["ema_fast"] > current["ema_slow"]) and (current["rsi"] > 55)

        if entry_condition:
             return "BUY", 1.0, {
                 "reason": "signal_triggered",
                 "rsi": current["rsi"],
                 "ema_fast": current["ema_fast"],
                 "ema_slow": current["ema_slow"]
             }

        return "HOLD", 0.0, {}

# Backtesting support wrapper
def generate_signal(df, client=None, symbol=None, params=None):
    return MCXStrategy.backtest_signal(df, params)

if __name__ == "__main__":
    MCXStrategy.cli()
