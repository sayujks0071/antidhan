#!/usr/bin/env python3
"""
MCX Silver Momentum Strategy
MCX Commodity trading strategy with RSI, ATR, and SMA analysis.
Refactored to use BaseStrategy.
"""
import os
import sys
import logging
import pandas as pd
from datetime import datetime, timedelta

# Add repo root to path to allow imports (if running as script)
try:
    from base_strategy import BaseStrategy
except ImportError:
    # Try setting path to find utils
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy

class MCXSilverMomentumStrategy(BaseStrategy):
    def __init__(self, symbol, quantity=1, api_key=None, host=None, ignore_time=False,
                 log_file=None, client=None, **kwargs):
        super().__init__(
            name="MCX_Silver_Momentum",
            symbol=symbol,
            quantity=quantity,
            interval="15m",
            exchange="MCX",
            api_key=api_key,
            host=host,
            ignore_time=ignore_time,
            log_file=log_file,
            client=client,
            **kwargs
        )

        # Strategy Parameters
        self.params = {
            'period_rsi': 14,
            'period_atr': 14,
            'sma_period': 50,
        }
        self.params.update(kwargs) # Add custom kwargs like seasonality_score

        self.last_candle_time = None

        self.logger.info(f"Initialized Strategy for {symbol}")
        self.logger.info(f"Filters: Seasonality={self.params.get('seasonality_score', 'N/A')}, "
                         f"USD_Vol={self.params.get('usd_inr_volatility', 'N/A')}")

    @classmethod
    def add_arguments(cls, parser):
        # Multi-Factor Arguments
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")
        parser.add_argument("--port", type=int, help="API Port (Override host)")


    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)

        # Handle Port/Host override
        if args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"

        # Add custom params to kwargs
        kwargs['usd_inr_trend'] = args.usd_inr_trend
        kwargs['usd_inr_volatility'] = args.usd_inr_volatility
        kwargs['seasonality_score'] = args.seasonality_score
        kwargs['global_alignment_score'] = args.global_alignment_score

        return kwargs

    def cycle(self):
        """
        Main Strategy Logic Execution Cycle
        """
        # Fetch Data
        df = self.fetch_history(days=10, interval="15m")
        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}: {len(df)} rows. Need >50.")
            return

        # Check for new candle to avoid intra-candle repainting/duplicate signals
        current_candle_time = df.iloc[-1]['datetime'] if 'datetime' in df.columns else df.index[-1]
        if self.last_candle_time and current_candle_time <= self.last_candle_time:
            # Candle has not closed or updated significantly (for 15m interval)
            # BaseStrategy loops every 60s, so we wait.
            return

        self.last_candle_time = current_candle_time
        self.logger.info(f"Processing Candle: {current_candle_time}")

        # Calculate Indicators
        # Use BaseStrategy methods where possible, or fallback to utils if series needed
        # BaseStrategy calculate_rsi returns series? No, let's check base_strategy.py again.
        # Yes: return calculate_rsi(series, period) -> utils.calculate_rsi -> returns Series (or float? Check utils)
        # Check trading_utils.py: calculate_rsi returns 100 - (100 / (1 + rs)) which is a Series.
        # Check BaseStrategy: wrapper calls it directly.

        df['rsi'] = self.calculate_rsi(df['close'], period=self.params['period_rsi'])
        # ATR: BaseStrategy.calculate_atr returns iloc[-1] (scalar). We want series?
        # If we need ATR for exit logic (stop loss dist), scalar is fine for current bar.
        # But if we want historical ATR?
        # Original code used: df["atr"] = calculate_atr(df, period=self.params["period_atr"])
        # This implies a series column.
        # I should import calculate_atr from trading_utils to get series.
        from trading_utils import calculate_atr, calculate_sma

        df['atr'] = calculate_atr(df, period=self.params['period_atr'])
        df['sma_50'] = calculate_sma(df['close'], period=self.params['sma_period'])

        current = df.iloc[-1]

        # Multi-Factor Checks
        seasonality_ok = self.params.get("seasonality_score", 50) > 40
        usd_vol = self.params.get("usd_inr_volatility", 0)
        usd_vol_high = usd_vol > 0.8

        # Position sizing adjustment for volatility
        base_qty = self.quantity # Futures usually 1 lot
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Trading effectively halted or reduced.")
            if usd_vol > 1.5:
                self.logger.warning("Volatility too high, skipping trade.")
                return

        if not seasonality_ok and not (self.pm and self.pm.has_position()):
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        close = current['close']
        sma_50 = current['sma_50']
        rsi = current['rsi']
        atr = current['atr']

        has_position = self.pm.has_position() if self.pm else False

        # Entry Logic
        if not has_position:
            # BUY
            if close > sma_50 and rsi > 55:
                self.logger.info(f"BUY SIGNAL: Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                self.execute_trade('BUY', base_qty, close)
            # SELL (Short)
            elif close < sma_50 and rsi < 45:
                self.logger.info(f"SELL SIGNAL: Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                self.execute_trade('SELL', base_qty, close)

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
                    exit_signal = True
                    exit_reason = "Stop Loss"
                elif close > (entry_price + take_profit_dist):
                    exit_signal = True
                    exit_reason = "Take Profit"
                elif close < sma_50 or rsi < 40:
                     exit_signal = True
                     exit_reason = "Trend Reversal"
            else: # Short
                if close > (entry_price + stop_loss_dist):
                    exit_signal = True
                    exit_reason = "Stop Loss"
                elif close < (entry_price - take_profit_dist):
                    exit_signal = True
                    exit_reason = "Take Profit"
                elif close > sma_50 or rsi > 60:
                    exit_signal = True
                    exit_reason = "Trend Reversal"

            if exit_signal:
                self.logger.info(f"EXIT ({exit_reason}): Price={close}")
                # Execute trade to close position
                side = "SELL" if is_long else "BUY"
                self.execute_trade(side, abs(pos_qty), close)

    def generate_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        # Re-calc locally for backtest
        from trading_utils import calculate_atr, calculate_sma, calculate_rsi

        df = df.copy()
        df["rsi"] = calculate_rsi(df["close"], period=self.params["period_rsi"])
        df["sma_50"] = calculate_sma(df["close"], period=self.params["sma_period"])

        current = df.iloc[-1]
        close = current['close']

        if pd.isna(current['sma_50']):
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

# Module level wrapper for SimpleBacktestEngine
def generate_signal(df, client=None, symbol=None, params=None):
    # Default params
    strat_params = {
        "period_rsi": 14,
        "period_atr": 14,
        "sma_period": 50,
    }
    if params:
        strat_params.update(params)

    # Use BaseStrategy-compatible init
    strat = MCXSilverMomentumStrategy(
        symbol=symbol or "TEST",
        quantity=1,
        api_key="BACKTEST",
        host="http://127.0.0.1:5001",
        client=client,
        **strat_params
    )

    # Silence logger
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    return strat.generate_signal(df)

if __name__ == "__main__":
    MCXSilverMomentumStrategy.cli()
