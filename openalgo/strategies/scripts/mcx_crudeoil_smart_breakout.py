#!/usr/bin/env python3
"""
[Strategy Description]
MCX Smart Breakout Strategy
Innovative volatility-adjusted breakout strategy with dynamic risk management.
Uses Bollinger Bands Squeeze/Expansion logic and ATR-based exits.
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

class MCXSmartStrategy(BaseStrategy):
    def __init__(self, symbol, api_key=None, host=None, **kwargs):
        super().__init__(
            name=f"MCX_Smart_{symbol}",
            symbol=symbol,
            api_key=api_key,
            host=host,
            exchange="MCX", # Default exchange
            interval="15m", # Default interval
            **kwargs
        )

        # Custom Parameters
        self.params = {
            "period_rsi": kwargs.get("period_rsi", 14),
            "period_atr": kwargs.get("period_atr", 14),
            "usd_inr_trend": kwargs.get("usd_inr_trend", "Neutral"),
            "usd_inr_volatility": float(kwargs.get("usd_inr_volatility", 0.0)),
            "seasonality_score": int(kwargs.get("seasonality_score", 50)),
            "global_alignment_score": int(kwargs.get("global_alignment_score", 50)),
        }

        self.last_candle_time = None
        self.data = pd.DataFrame()

        self.logger.info(f"Filters: Seasonality={self.params['seasonality_score']}, USD_Vol={self.params['usd_inr_volatility']}")

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        # Legacy port argument support
        parser.add_argument("--port", type=int, help="API Port (Legacy support)")

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        # Pass custom args to kwargs
        if hasattr(args, 'usd_inr_trend'): kwargs['usd_inr_trend'] = args.usd_inr_trend
        if hasattr(args, 'usd_inr_volatility'): kwargs['usd_inr_volatility'] = args.usd_inr_volatility
        if hasattr(args, 'seasonality_score'): kwargs['seasonality_score'] = args.seasonality_score
        if hasattr(args, 'global_alignment_score'): kwargs['global_alignment_score'] = args.global_alignment_score
        if hasattr(args, 'period_rsi'): kwargs['period_rsi'] = args.period_rsi

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

        # Check if we have a new candle
        if not self.check_new_candle(df):
            return

        self.data = df

        # Calculate Indicators locally
        df['sma_50'] = self.calculate_sma(df['close'], period=50)
        df['rsi'] = self.calculate_rsi(df['close'], period=self.params.get("period_rsi", 14))
        df['bb_mid'], df['bb_upper'], df['bb_lower'] = self.calculate_bollinger_bands(df['close'], window=20, num_std=2)

        # ATR 14
        df['atr'] = self.calculate_atr_series(df, period=14)
        df['atr_ma'] = self.calculate_sma(df['atr'], period=10)

        current = df.iloc[-1]

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.params["seasonality_score"] > 40
        usd_vol_high = self.params["usd_inr_volatility"] > 1.0

        # Position sizing adjustment for volatility
        base_qty = self.quantity
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # ---------------------------------------------------------
        # INNOVATIVE LOGIC: Volatility-Adjusted Breakout
        # ---------------------------------------------------------

        # Volatility Check: Is current ATR > Average ATR? (Market is waking up)
        volatility_expanding = current['atr'] > current['atr_ma']

        # Trend Filter: Long only if price > SMA 50, Short only if price < SMA 50
        trend_up = current['close'] > current['sma_50']
        trend_down = current['close'] < current['sma_50']

        # Entry Logic
        if not has_position:
            # BUY: Price breaks Upper BB, Volatility Expanding, RSI Healthy (50-70)
            if (current['close'] > current['bb_upper'] and
                volatility_expanding and
                trend_up and
                50 < current['rsi'] < 70):

                stop_loss = current['close'] - (1.5 * current['atr'])
                take_profit = current['close'] + (3.0 * current['atr'])

                self.logger.info(f"BUY SIGNAL (Smart Breakout): Price={current['close']}, ATR={current['atr']:.2f}, SL={stop_loss:.2f}, TP={take_profit:.2f}")

                self.execute_trade("BUY", base_qty, current['close'])

            # SELL: Price breaks Lower BB, Volatility Expanding, RSI Healthy (30-50)
            elif (current['close'] < current['bb_lower'] and
                  volatility_expanding and
                  trend_down and
                  30 < current['rsi'] < 50):

                stop_loss = current['close'] + (1.5 * current['atr'])
                take_profit = current['close'] - (3.0 * current['atr'])

                self.logger.info(f"SELL SIGNAL (Smart Breakdown): Price={current['close']}, ATR={current['atr']:.2f}, SL={stop_loss:.2f}, TP={take_profit:.2f}")

                self.execute_trade("SELL", base_qty, current['close'])

        # Exit Logic
        elif has_position:
            if not self.pm: return

            pos_qty = self.pm.position
            entry_price = self.pm.entry_price

            if pos_qty > 0: # Long Position
                # Stop Loss: Close below SMA 20 (Trailing) OR Hard ATR Stop
                stop_hit = current['close'] < (entry_price - (1.5 * current['atr']))
                trend_reversal = current['close'] < current['bb_mid'] # SMA 20 is BB Mid
                target_hit = current['close'] > (entry_price + (3.0 * current['atr']))

                if stop_hit or trend_reversal or target_hit:
                    reason = "Stop Loss" if stop_hit else "Target" if target_hit else "Trend Reversal"
                    self.logger.info(f"EXIT LONG ({reason}): Price={current['close']}, Entry={entry_price}")
                    self.execute_trade("SELL", abs(pos_qty), current['close'])

            elif pos_qty < 0: # Short Position
                # Stop Loss
                stop_hit = current['close'] > (entry_price + (1.5 * current['atr']))
                trend_reversal = current['close'] > current['bb_mid']
                target_hit = current['close'] < (entry_price - (3.0 * current['atr']))

                if stop_hit or trend_reversal or target_hit:
                    reason = "Stop Loss" if stop_hit else "Target" if target_hit else "Trend Reversal"
                    self.logger.info(f"EXIT SHORT ({reason}): Price={current['close']}, Entry={entry_price}")
                    self.execute_trade("BUY", abs(pos_qty), current['close'])

    def get_signal(self, df):
        """Backtesting signal generation"""
        if df.empty:
            return "HOLD", 0.0, {}

        # We need indicators.
        df = df.copy()
        df['sma_50'] = self.calculate_sma(df['close'], period=50)
        df['rsi'] = self.calculate_rsi(df['close'], period=self.params.get("period_rsi", 14))
        df['bb_mid'], df['bb_upper'], df['bb_lower'] = self.calculate_bollinger_bands(df['close'], window=20, num_std=2)
        df['atr'] = self.calculate_atr_series(df, period=14)
        df['atr_ma'] = self.calculate_sma(df['atr'], period=10)

        if len(df) < 50:
            return "HOLD", 0.0, {}

        current = df.iloc[-1]

        # Logic mirroring check_signals
        volatility_expanding = current['atr'] > current['atr_ma']
        trend_up = current['close'] > current['sma_50']
        trend_down = current['close'] < current['sma_50']

        if (current['close'] > current['bb_upper'] and
            volatility_expanding and
            trend_up and
            50 < current['rsi'] < 70):
            return "BUY", 1.0, {"reason": "Smart Breakout"}

        elif (current['close'] < current['bb_lower'] and
              volatility_expanding and
              trend_down and
              30 < current['rsi'] < 50):
            return "SELL", 1.0, {"reason": "Smart Breakdown"}

        return "HOLD", 0.0, {}

# Backtesting alias
generate_signal = MCXSmartStrategy.backtest_signal

if __name__ == "__main__":
    MCXSmartStrategy.cli()
