#!/usr/bin/env python3
"""
MCX Natural Gas Momentum Strategy
MCX Commodity trading strategy with multi-factor analysis (RSI, ADX, SMA, Seasonality).
Refactored to use BaseStrategy.
"""
import os
import sys
import logging

# Add repo root to path
try:
    from base_strategy import BaseStrategy
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy

class MCXNaturalGasStrategy(BaseStrategy):
    def __init__(self, symbol, api_key=None, host=None, **kwargs):
        super().__init__(
            name=f"MCX_NG_{symbol}",
            symbol=symbol,
            api_key=api_key,
            host=host,
            exchange="MCX",
            interval="15m",
            type="FUT",
            **kwargs
        )

        # Strategy Parameters
        self.period_rsi = int(kwargs.get('period_rsi', 14))
        self.period_atr = int(kwargs.get('period_atr', 14))
        self.period_adx = int(kwargs.get('period_adx', 14))

        self.rsi_buy = int(kwargs.get('rsi_buy', 55))
        self.rsi_sell = int(kwargs.get('rsi_sell', 45))
        self.adx_threshold = int(kwargs.get('adx_threshold', 25))

        # Multi-Factor Parameters
        self.usd_inr_trend = kwargs.get('usd_inr_trend', "Neutral")
        self.usd_inr_volatility = float(kwargs.get('usd_inr_volatility', 0.0))
        self.seasonality_score = int(kwargs.get('seasonality_score', 50))
        self.global_alignment_score = int(kwargs.get('global_alignment_score', 50))

        self.logger.info(f"Filters: Seasonality={self.seasonality_score}, USD_Vol={self.usd_inr_volatility}")

    @classmethod
    def add_arguments(cls, parser):
        # Strategy Parameters
        parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
        parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
        parser.add_argument("--period_adx", type=int, default=14, help="ADX Period")

        parser.add_argument("--rsi_buy", type=int, default=55, help="RSI Buy Threshold")
        parser.add_argument("--rsi_sell", type=int, default=45, help="RSI Sell Threshold")
        parser.add_argument("--adx_threshold", type=int, default=25, help="ADX Threshold")

        # Multi-Factor Arguments
        parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
        parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
        parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
        parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

        # Legacy port argument support
        parser.add_argument("--port", type=int, help="API Port (Legacy support)")

    @classmethod
    def parse_arguments(cls, args):
        # Set default exchange to MCX for SymbolResolver logic
        if not hasattr(args, 'exchange') or not args.exchange:
            args.exchange = "MCX"
        if not hasattr(args, 'type') or not args.type:
            args.type = "FUT"

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

    def get_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty or len(df) < 50:
            return "HOLD", 0.0, {}

        # Indicators
        try:
            df = df.copy()
            df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
            df["sma_20"] = self.calculate_sma(df["close"], period=20)
            df["sma_50"] = self.calculate_sma(df["close"], period=50)
            df["adx"] = self.calculate_adx_series(df, period=self.period_adx)
        except Exception as e:
            return "HOLD", 0.0, {"error": str(e)}

        current = df.iloc[-1]

        # Signal Logic
        # BUY: Price > SMA20 > SMA50, RSI > Buy, ADX > Thresh
        if (current['close'] > current['sma_20'] > current['sma_50']) and \
           (current['rsi'] > self.rsi_buy) and \
           (current['adx'] > self.adx_threshold):
            return "BUY", 1.0, {"reason": "Trend_Momentum_Buy", "rsi": current['rsi'], "adx": current['adx']}

        # SELL: Price < SMA20 < SMA50, RSI < Sell, ADX > Thresh
        elif (current['close'] < current['sma_20'] < current['sma_50']) and \
             (current['rsi'] < self.rsi_sell) and \
             (current['adx'] > self.adx_threshold):
            return "SELL", 1.0, {"reason": "Trend_Momentum_Sell", "rsi": current['rsi'], "adx": current['adx']}

        return "HOLD", 0.0, {}

    def cycle(self):
        """Main execution cycle"""
        # Fetch Data
        df = self.fetch_history(days=5, interval=self.interval, exchange=self.exchange)

        if not self.check_new_candle(df):
             return

        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}.")
            return

        # Calculate Indicators locally
        try:
            df["rsi"] = self.calculate_rsi(df["close"], period=self.period_rsi)
            df["sma_20"] = self.calculate_sma(df["close"], period=20)
            df["sma_50"] = self.calculate_sma(df["close"], period=50)
            df["adx"] = self.calculate_adx_series(df, period=self.period_adx)
            df["atr"] = self.calculate_atr_series(df, period=self.period_atr)
        except Exception as e:
            self.logger.error(f"Indicator Error: {e}")
            return

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
            self.logger.warning("⚠️ High USD/INR Volatility: Reducing position size (Simulated).")
            # Futures usually minimum 1 lot, so we just log warning or reduce if > 1
            if base_qty > 1:
                base_qty = max(1, int(base_qty * 0.7))

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

# Backtesting alias
generate_signal = MCXNaturalGasStrategy.backtest_signal

if __name__ == "__main__":
    MCXNaturalGasStrategy.cli()
