#!/usr/bin/env python3
"""
NSE RSI MACD Strategy
Strategy for NSE Equities using RSI and MACD for Trend Following.
Entry: Buy when MACD Line crosses above Signal Line AND RSI > 50.
Exit: Sell when MACD Line crosses below Signal Line OR RSI > 70.
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

class NSERsiMacdStrategy(BaseStrategy):
    def __init__(self, symbol, api_key=None, host=None, **kwargs):
        super().__init__(
            name=f"NSE_RSI_MACD_{symbol}",
            symbol=symbol,
            api_key=api_key,
            host=host,
            exchange="NSE",
            interval="5m",
            **kwargs
        )

        # Strategy parameters
        self.rsi_period = int(kwargs.get('rsi_period', 14))
        self.macd_fast = int(kwargs.get('macd_fast', 12))
        self.macd_slow = int(kwargs.get('macd_slow', 26))
        self.macd_signal = int(kwargs.get('macd_signal', 9))

        self.logger.info(f"Params: RSI={self.rsi_period}, MACD=({self.macd_fast},{self.macd_slow},{self.macd_signal})")

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--rsi_period', type=int, default=14, help='RSI Period')
        parser.add_argument('--macd_fast', type=int, default=12, help='MACD Fast Period')
        parser.add_argument('--macd_slow', type=int, default=26, help='MACD Slow Period')
        parser.add_argument('--macd_signal', type=int, default=9, help='MACD Signal Period')
        # Legacy port argument support
        parser.add_argument("--port", type=int, help="API Port (Legacy support)")

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        if hasattr(args, 'rsi_period'): kwargs['rsi_period'] = args.rsi_period
        if hasattr(args, 'macd_fast'): kwargs['macd_fast'] = args.macd_fast
        if hasattr(args, 'macd_slow'): kwargs['macd_slow'] = args.macd_slow
        if hasattr(args, 'macd_signal'): kwargs['macd_signal'] = args.macd_signal

        # Support legacy --port arg by constructing host
        if hasattr(args, 'port') and args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"

        return kwargs

    def get_signal(self, df):
        """Calculate signal for backtesting support"""
        if df.empty or len(df) < max(self.macd_slow, self.rsi_period) + 5:
            return 'HOLD', 0.0, {}

        # Calculate indicators
        try:
            # Use BaseStrategy's wrappers which use trading_utils
            # But BaseStrategy doesn't have macd wrapper explicitly returning series in the same way?
            # BaseStrategy.calculate_macd returns (macd, signal, hist)

            df = df.copy()
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            macd, signal_line, _ = self.calculate_macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
            df['macd'] = macd
            df['signal'] = signal_line
        except Exception as e:
            # Fallback
            return 'HOLD', 0.0, {"error": str(e)}

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Entry logic: Buy if MACD Crosses Above Signal AND RSI > 50
        # Check crossover: prev MACD <= prev Signal AND curr MACD > curr Signal
        bullish_crossover = (prev['macd'] <= prev['signal']) and (last['macd'] > last['signal'])

        if bullish_crossover and last['rsi'] > 50:
            return 'BUY', 1.0, {
                'reason': 'MACD Crossover + RSI Trend',
                'price': last['close'],
                'rsi': last['rsi'],
                'macd': last['macd']
            }

        # Exit logic: Sell if MACD Crosses Below Signal OR RSI > 70
        bearish_crossover = (prev['macd'] >= prev['signal']) and (last['macd'] < last['signal'])

        if bearish_crossover or last['rsi'] > 70:
             return 'SELL', 1.0, {
                'reason': 'MACD Reversal / Overbought',
                'price': last['close'],
                'rsi': last['rsi'],
                'macd': last['macd']
            }

        return 'HOLD', 0.0, {}

    def cycle(self):
        """Main execution cycle"""
        # Determine exchange (NSE for stocks, NSE_INDEX for indices)
        exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"

        # Update exchange if needed (BaseStrategy defaults to NSE)
        if self.exchange != exchange:
            self.exchange = exchange

        # Fetch historical data
        df = self.fetch_history(days=5, interval=self.interval, exchange=self.exchange)

        if not self.check_new_candle(df):
             return

        if df.empty or len(df) < max(self.macd_slow, self.rsi_period):
            self.logger.warning("Insufficient data.")
            return

        # Calculate indicators locally
        try:
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            macd, signal_line, _ = self.calculate_macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
            df['macd'] = macd
            df['signal'] = signal_line
        except Exception as e:
            self.logger.error(f"Indicator Error: {e}")
            return

        last = df.iloc[-1]
        prev = df.iloc[-2]
        current_price = last['close']
        current_rsi = last['rsi']
        current_macd = last['macd']
        current_signal = last['signal']

        self.logger.info(f"Price: {current_price}, RSI: {current_rsi:.2f}, MACD: {current_macd:.2f}, Signal: {current_signal:.2f}")

        # Position management
        if self.pm and self.pm.has_position():
            # Exit logic
            pnl = self.pm.get_pnl(current_price)

            # Exit if MACD Crosses Below Signal OR RSI > 70
            bearish_crossover = (prev['macd'] >= prev['signal']) and (last['macd'] < last['signal'])

            if bearish_crossover or current_rsi > 70:
                reason = "MACD Cross Under" if bearish_crossover else "RSI Overbought"
                self.logger.info(f"Exiting position. PnL: {pnl:.2f}. Reason: {reason}")
                self.execute_trade('SELL', abs(self.pm.position), current_price)
        else:
            # Entry logic
            # Buy if MACD Crosses Above Signal AND RSI > 50
            bullish_crossover = (prev['macd'] <= prev['signal']) and (last['macd'] > last['signal'])

            if bullish_crossover and current_rsi > 50:
                # Use BaseStrategy's adaptive quantity logic
                qty = self.get_adaptive_quantity(current_price)

                self.logger.info(f"Entry signal detected (Bullish Trend). Buying {qty} at {current_price}")
                self.execute_trade('BUY', qty, current_price)

# Backtesting alias
generate_signal = NSERsiMacdStrategy.backtest_signal

if __name__ == "__main__":
    NSERsiMacdStrategy.cli()
