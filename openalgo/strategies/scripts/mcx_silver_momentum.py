#!/usr/bin/env python3
"""
MCX Silver Momentum Strategy
MCX Commodity trading strategy with RSI, ATR, and SMA analysis.
Refactored to inherit from BaseStrategy.
"""
import os
import sys
import logging
import pandas as pd

# Add repo root to path to allow imports (if running as script)
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(current_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol
except ImportError:
    pass

class MCXStrategy(BaseStrategy):
    def __init__(self, symbol, quantity=1, api_key=None, host=None, params=None, **kwargs):
        super().__init__(
            name="MCX_Silver_Momentum",
            symbol=symbol,
            quantity=quantity,
            interval="15m",
            exchange="MCX",
            api_key=api_key,
            host=host,
            sleep_time=900, # 15 minutes loop
            **kwargs
        )
        self.params = params or {}

        self.logger.info(f"Initialized Strategy for {self.symbol}")
        self.logger.info(f"Filters: Seasonality={self.params.get('seasonality_score', 'N/A')}, USD_Vol={self.params.get('usd_inr_volatility', 'N/A')}")

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--underlying", type=str, help="Commodity Name (e.g., GOLD, SILVER)")
        # Multi-Factor Arguments
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)

        # Build params dict
        params = {
            "period_rsi": 14,
            "period_atr": 14,
            "usd_inr_trend": getattr(args, 'usd_inr_trend', "Neutral"),
            "usd_inr_volatility": getattr(args, 'usd_inr_volatility', 0.0),
            "seasonality_score": getattr(args, 'seasonality_score', 50),
            "global_alignment_score": getattr(args, 'global_alignment_score', 50),
        }
        kwargs['params'] = params

        # Set quantity default for MCX (usually 1 lot)
        if not kwargs.get('quantity'):
            kwargs['quantity'] = 1

        return kwargs

    def cycle(self):
        """
        Main Strategy Logic
        """
        # Fetch Data (15m)
        df = self.fetch_history(days=10, interval="15m")

        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}: {len(df)} candles.")
            return

        # Calculate Indicators
        df['rsi'] = self.calculate_rsi(df['close'], period=self.params.get("period_rsi", 14))
        # Get ATR Series for dataframe
        df['atr'] = self.calculate_atr(df, period=self.params.get("period_atr", 14), mode='series')

        # Get current ATR scalar for logic
        atr = df['atr'].iloc[-1]

        df['sma_50'] = self.calculate_sma(df['close'], period=50)

        current = df.iloc[-1]

        # Check Signals
        self.check_and_execute(current, atr)

    def check_and_execute(self, current, atr):
        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.params.get("seasonality_score", 50) > 40
        usd_vol = self.params.get("usd_inr_volatility", 0)
        usd_vol_high = usd_vol > 0.8

        # Position sizing adjustment for volatility
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Trading effectively halted or reduced.")
            if usd_vol > 1.5:
                self.logger.warning("Volatility too high, skipping trade.")
                return

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        close = current['close']
        sma_50 = current['sma_50']
        rsi = current['rsi']

        # Entry Logic
        if not has_position:
            # BUY
            if close > sma_50 and rsi > 55:
                self.logger.info(f"BUY SIGNAL: Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                self.execute_trade("BUY", self.quantity, close)
            # SELL (Short)
            elif close < sma_50 and rsi < 45:
                self.logger.info(f"SELL SIGNAL: Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                self.execute_trade("SELL", self.quantity, close)

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price

            is_long = pos_qty > 0

            stop_loss_dist = 2 * atr
            take_profit_dist = 4 * atr

            exit_signal = False
            exit_reason = ""

            if is_long:
                if close < (entry_price - stop_loss_dist):
                    exit_signal = True; exit_reason = "Stop Loss"
                elif close > (entry_price + take_profit_dist):
                    exit_signal = True; exit_reason = "Take Profit"
                elif close < sma_50 or rsi < 40:
                     exit_signal = True; exit_reason = "Trend Reversal"

                if exit_signal:
                    self.logger.info(f"EXIT ({exit_reason}): Price={close}")
                    self.execute_trade("SELL", abs(pos_qty), close)

            else: # Short
                if close > (entry_price + stop_loss_dist):
                    exit_signal = True; exit_reason = "Stop Loss"
                elif close < (entry_price - take_profit_dist):
                    exit_signal = True; exit_reason = "Take Profit"
                elif close > sma_50 or rsi > 60:
                    exit_signal = True; exit_reason = "Trend Reversal"

                if exit_signal:
                    self.logger.info(f"EXIT ({exit_reason}): Price={close}")
                    self.execute_trade("BUY", abs(pos_qty), close)

    def generate_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        # Indicators
        df['rsi'] = self.calculate_rsi(df['close'], period=self.params.get("period_rsi", 14))
        df['sma_50'] = self.calculate_sma(df['close'], period=50)

        current = df.iloc[-1]

        close = current['close']
        # Check if 'sma_50' exists (might not if not enough data)
        if 'sma_50' not in current or pd.isna(current['sma_50']):
             return "HOLD", 0.0, {}

        sma_50 = current['sma_50']
        rsi = current['rsi']

        # BUY
        if close > sma_50 and rsi > 55:
            return "BUY", 1.0, {"reason": f"Price > SMA50 & RSI({rsi:.1f}) > 55"}

        # SELL (Short)
        if close < sma_50 and rsi < 45:
             return "SELL", 1.0, {"reason": f"Price < SMA50 & RSI({rsi:.1f}) < 45"}

        return "HOLD", 0.0, {}

# Backtesting support
DEFAULT_PARAMS = {
    "period_rsi": 14,
    "period_atr": 14,
}
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = DEFAULT_PARAMS.copy()
    if params:
        strat_params.update(params)

    api_key = client.api_key if client and hasattr(client, "api_key") else "BACKTEST"
    host = client.host if client and hasattr(client, "host") else "http://127.0.0.1:5001"

    # Instantiate strategy
    strat = MCXStrategy(symbol=symbol or "TEST", api_key=api_key, host=host, params=strat_params)
    return strat.generate_signal(df)

if __name__ == "__main__":
    MCXStrategy.cli()
