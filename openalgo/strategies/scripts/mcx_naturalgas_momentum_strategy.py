#!/usr/bin/env python3
"""
[Strategy Description]
MCX Commodity trading strategy with multi-factor analysis
MCX Natural Gas Momentum Strategy: Uses RSI, ADX, and SMA crossovers to identify trend strength and direction.
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

class MCXNaturalGasMomentumStrategy(BaseStrategy):
    def __init__(self, symbol, api_key=None, host=None, **kwargs):
        super().__init__(
            name=f"MCX_NG_Momentum_{symbol}",
            symbol=symbol,
            api_key=api_key,
            host=host,
            exchange="MCX",
            interval="15m",
            **kwargs
        )

        # Strategy Parameters
        self.period_rsi = int(kwargs.get("period_rsi", 14))
        self.period_atr = int(kwargs.get("period_atr", 14))
        self.period_adx = int(kwargs.get("period_adx", 14))
        self.rsi_buy = float(kwargs.get("rsi_buy", 55))
        self.rsi_sell = float(kwargs.get("rsi_sell", 45))
        self.adx_threshold = float(kwargs.get("adx_threshold", 25))

        # Multi-Factor Parameters
        self.usd_inr_trend = kwargs.get("usd_inr_trend", "Neutral")
        self.usd_inr_volatility = float(kwargs.get("usd_inr_volatility", 0.0))
        self.seasonality_score = int(kwargs.get("seasonality_score", 50))
        self.global_alignment_score = int(kwargs.get("global_alignment_score", 50))

        self.data = pd.DataFrame()

        self.logger.info(f"Initialized Strategy for {symbol}")
        self.logger.info(f"Filters: Seasonality={self.seasonality_score}, USD_Vol={self.usd_inr_volatility}")

    @classmethod
    def add_arguments(cls, parser):
        # Strategy Parameters
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--period_adx", type=int, default=14, help="ADX Period")
        parser.add_argument("--rsi_buy", type=float, default=55, help="RSI Buy Threshold")
        parser.add_argument("--rsi_sell", type=float, default=45, help="RSI Sell Threshold")
        parser.add_argument("--adx_threshold", type=float, default=25, help="ADX Threshold")

        # Multi-Factor Arguments
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

        # Legacy port argument support
        parser.add_argument("--port", type=int, help="API Port (Legacy support)")

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        if hasattr(args, 'period_rsi'): kwargs['period_rsi'] = args.period_rsi
        if hasattr(args, 'period_atr'): kwargs['period_atr'] = args.period_atr
        if hasattr(args, 'period_adx'): kwargs['period_adx'] = args.period_adx
        if hasattr(args, 'rsi_buy'): kwargs['rsi_buy'] = args.rsi_buy
        if hasattr(args, 'rsi_sell'): kwargs['rsi_sell'] = args.rsi_sell
        if hasattr(args, 'adx_threshold'): kwargs['adx_threshold'] = args.adx_threshold

        if hasattr(args, 'usd_inr_trend'): kwargs['usd_inr_trend'] = args.usd_inr_trend
        if hasattr(args, 'usd_inr_volatility'): kwargs['usd_inr_volatility'] = args.usd_inr_volatility
        if hasattr(args, 'seasonality_score'): kwargs['seasonality_score'] = args.seasonality_score
        if hasattr(args, 'global_alignment_score'): kwargs['global_alignment_score'] = args.global_alignment_score

        # Support legacy --port arg by constructing host
        if hasattr(args, 'port') and args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"

        return kwargs

    def cycle(self):
        """Check entry and exit conditions"""
        # Fetch Data
        df = self.fetch_history(days=10, interval="15m")
        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}.")
            return

        if not self.check_new_candle(df):
            return

        self.data = df

        # Calculate Indicators locally
        df = df.copy()
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
        df["atr"] = self.calculate_atr_series(df, period=self.period_atr)
        df["sma_20"] = self.calculate_sma(df["close"], period=20)
        df["sma_50"] = self.calculate_sma(df["close"], period=50)
        df["adx"] = self.calculate_adx_series(df, period=self.period_adx)

        current = df.iloc[-1]

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        base_qty = self.quantity
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size (Simulated - Futures min lot is 1).")
            # In real scenario, we might skip trade or hedge. For now, we log.
            # base_qty = max(1, int(base_qty * 0.7))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic
        if not has_position:
            # BUY Entry
            if (current['close'] > current['sma_20'] > current['sma_50']) and \
               (current['rsi'] > self.rsi_buy) and \
               (current['adx'] > self.adx_threshold):

                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                self.execute_trade("BUY", base_qty, current['close'])

            # SELL Entry
            elif (current['close'] < current['sma_20'] < current['sma_50']) and \
                 (current['rsi'] < self.rsi_sell) and \
                 (current['adx'] > self.adx_threshold):

                self.logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                self.execute_trade("SELL", base_qty, current['close'])

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position

            # BUY Exit
            if pos_qty > 0:
                if (current['close'] < current['sma_20']) or (current['rsi'] < 40):
                    self.logger.info(f"EXIT BUY: Trend Faded (Price < SMA20 or RSI < 40)")
                    self.execute_trade("SELL", abs(pos_qty), current['close'])

            # SELL Exit
            elif pos_qty < 0:
                if (current['close'] > current['sma_20']) or (current['rsi'] > 60):
                    self.logger.info(f"EXIT SELL: Trend Faded (Price > SMA20 or RSI > 60)")
                    self.execute_trade("BUY", abs(pos_qty), current['close'])

    def get_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        df = df.copy()
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
        df["sma_20"] = self.calculate_sma(df["close"], period=20)
        df["sma_50"] = self.calculate_sma(df["close"], period=50)
        df["adx"] = self.calculate_adx_series(df, period=self.period_adx)

        current = df.iloc[-1]

        # Signal Logic
        if (current['close'] > current['sma_20'] > current['sma_50']) and \
           (current['rsi'] > self.rsi_buy) and \
           (current['adx'] > self.adx_threshold):
            return "BUY", 1.0, {"reason": "Trend_Momentum_Buy", "rsi": current['rsi'], "adx": current['adx']}

        elif (current['close'] < current['sma_20'] < current['sma_50']) and \
             (current['rsi'] < self.rsi_sell) and \
             (current['adx'] > self.adx_threshold):
            return "SELL", 1.0, {"reason": "Trend_Momentum_Sell", "rsi": current['rsi'], "adx": current['adx']}

        return "HOLD", 0.0, {}

# Backtesting alias
generate_signal = MCXNaturalGasMomentumStrategy.backtest_signal

if __name__ == "__main__":
    MCXNaturalGasMomentumStrategy.cli()
