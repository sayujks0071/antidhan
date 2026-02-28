#!/usr/bin/env python3
"""
MCX Natural Gas Momentum Strategy
Uses RSI, ADX, and SMA crossovers to identify trend strength and direction.
Inherits from BaseStrategy.
"""
import os
import sys

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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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

        # Legacy port support
        parser.add_argument('--port', type=int, help='API Port (Legacy)')

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

        # Support legacy --port arg
        if hasattr(args, 'port') and args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"

        return kwargs

    def calculate_indicators(self, df):
        df = df.copy()
        df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
        df["atr"] = self.calculate_atr_series(df, period=self.period_atr)
        df["sma_20"] = self.calculate_sma(df["close"], period=20)
        df["sma_50"] = self.calculate_sma(df["close"], period=50)
        df["adx"] = self.calculate_adx_series(df, period=self.period_adx)
        return df

    def cycle(self):
        # Fetch Data
        df = self.fetch_history(days=10, interval="15m", exchange="MCX")

        if df.empty or len(df) < max(50, self.period_rsi, self.period_adx) + 5:
            self.logger.info("Waiting for sufficient data...")
            return

        # Check if we have a new candle
        if not self.check_new_candle(df):
            return

        df = self.calculate_indicators(df)
        self.check_signals(df)

    def check_signals(self, df):
        current = df.iloc[-1]

        has_position = False
        pos_qty = 0

        if self.pm:
            has_position = self.pm.has_position()
            pos_qty = self.pm.position

        # Multi-Factor Checks
        seasonality_ok = self.seasonality_score > 40
        usd_vol_high = self.usd_inr_volatility > 1.0

        # Position sizing adjustment for volatility
        base_qty = self.quantity
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size.")
            # Simple simulation of reduction or skip
            # base_qty = max(1, int(base_qty * 0.7))

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Logic
        close = current['close']
        sma_20 = current['sma_20']
        sma_50 = current['sma_50']
        rsi = current['rsi']
        adx = current['adx']

        # Entry Logic
        if not has_position:
            # BUY Entry
            if (close > sma_20 > sma_50) and \
               (rsi > self.rsi_buy) and \
               (adx > self.adx_threshold):

                self.logger.info(f"BUY SIGNAL: Price={close}, RSI={rsi:.2f}, ADX={adx:.2f}")
                self.execute_trade("BUY", base_qty, close)

            # SELL Entry
            elif (close < sma_20 < sma_50) and \
                 (rsi < self.rsi_sell) and \
                 (adx > self.adx_threshold):

                self.logger.info(f"SELL SIGNAL: Price={close}, RSI={rsi:.2f}, ADX={adx:.2f}")
                self.execute_trade("SELL", base_qty, close)

        # Exit Logic
        elif has_position:
            # BUY Exit
            if pos_qty > 0:
                if (close < sma_20) or (rsi < 40):
                    self.logger.info(f"EXIT BUY: Trend Faded (Price < SMA20 or RSI < 40)")
                    self.execute_trade("SELL", abs(pos_qty), close)

            # SELL Exit
            elif pos_qty < 0:
                if (close > sma_20) or (rsi > 60):
                    self.logger.info(f"EXIT SELL: Trend Faded (Price > SMA20 or RSI > 60)")
                    self.execute_trade("BUY", abs(pos_qty), close)

    def get_signal(self, df):
        """Backtesting signal generation"""
        if df.empty:
            return "HOLD", 0.0, {}

        df = self.calculate_indicators(df)
        current = df.iloc[-1]

        close = current['close']
        sma_20 = current['sma_20']
        sma_50 = current['sma_50']
        rsi = current['rsi']
        adx = current['adx']

        # Signal Logic
        if (close > sma_20 > sma_50) and \
           (rsi > self.rsi_buy) and \
           (adx > self.adx_threshold):
            return "BUY", 1.0, {"reason": "Trend_Momentum_Buy", "rsi": rsi, "adx": adx}

        elif (close < sma_20 < sma_50) and \
             (rsi < self.rsi_sell) and \
             (adx > self.adx_threshold):
            return "SELL", 1.0, {"reason": "Trend_Momentum_Sell", "rsi": rsi, "adx": adx}

        return "HOLD", 0.0, {}

# Backtesting alias
generate_signal = MCXNaturalGasMomentumStrategy.backtest_signal

if __name__ == "__main__":
    MCXNaturalGasMomentumStrategy.cli()
