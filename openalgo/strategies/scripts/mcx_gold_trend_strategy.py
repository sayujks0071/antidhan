#!/usr/bin/env python3
"""
MCX Gold Trend Strategy
MCX Commodity trading strategy with SMA (20/50), RSI, and ADX analysis
Inherits from BaseStrategy for consistent infrastructure usage.
"""
import strategy_preamble
from base_strategy import BaseStrategy

class MCXGoldTrendStrategy(BaseStrategy):
    def setup(self):
        # Default Parameters
        self.period_rsi = getattr(self, "period_rsi", 14)
        self.period_atr = getattr(self, "period_atr", 14)
        self.period_sma_fast = getattr(self, "period_sma_fast", 20)
        self.period_sma_slow = getattr(self, "period_sma_slow", 50)
        self.period_adx = getattr(self, "period_adx", 14)

        # Multi-Factor Parameters
        self.seasonality_score = getattr(self, "seasonality_score", 50)
        self.usd_inr_volatility = getattr(self, "usd_inr_volatility", 0.0)
        self.global_alignment_score = getattr(self, "global_alignment_score", 50)

        # Default interval for MCX Gold
        if self.interval == "5m":
            self.interval = "15m"

        # Default exchange for MCX Gold
        if self.exchange == "NSE":
            self.exchange = "MCX"

        # Declarative Indicators
        self.indicators = {
            'rsi': self.period_rsi,
            'atr': self.period_atr,
            'sma': [self.period_sma_fast, self.period_sma_slow],
            'adx': self.period_adx
        }

    def generate_signal(self, df):
        """
        Generate signal using pre-calculated indicators.
        """
        current = df.iloc[-1]

        # Map indicators
        sma_fast = current[f'sma_{self.period_sma_fast}']
        sma_slow = current[f'sma_{self.period_sma_slow}']
        rsi = current['rsi']
        adx = current['adx']
        atr_val = current['atr']

        # Position Management
        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return "HOLD"

        # Entry Logic
        buy_signal = (sma_fast > sma_slow) and (rsi > 50) and (adx > 25)
        sell_signal = (sma_fast < sma_slow) and (rsi < 50) and (adx > 25)

        if not has_position:
            if buy_signal or sell_signal:
                # Adaptive Sizing using Monthly ATR via BaseStrategy
                qty = self.get_adaptive_quantity(current['close'], risk_pct=1.0, capital=500000)

                # Apply modifier for USD Volatility
                if usd_vol_high:
                    self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
                    qty = max(1, int(qty * 0.7))

                action = "BUY" if buy_signal else "SELL"
                self.logger.info(f"{action} SIGNAL: Price={current['close']}, RSI={rsi:.2f}, ADX={adx:.2f}")
                return action, qty

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price

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
                elif (sma_fast < sma_slow): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"
            elif pos_qty < 0: # Short
                if (current["close"] <= entry_price - target):
                    exit_signal = True
                    reason = "Target Hit"
                elif (current["close"] >= entry_price + stop):
                    exit_signal = True
                    reason = "Stop Loss Hit"
                elif (sma_fast > sma_slow): # Trend Reversal
                    exit_signal = True
                    reason = "Trend Reversal"

            if exit_signal:
                self.logger.info(f"EXIT: {reason}")
                return "EXIT"

        return "HOLD"

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")

if __name__ == "__main__":
    MCXGoldTrendStrategy.cli()
