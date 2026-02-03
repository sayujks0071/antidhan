#!/usr/bin/env python3
"""
MCX Commodity Momentum Strategy
Momentum strategy using ADX and RSI with proper API integration.
Enhanced with Multi-Factor inputs (USD/INR, Seasonality).
"""
import os
import sys
import logging

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

class MCXMomentumStrategy(BaseStrategy):
    def __init__(self, symbol, quantity, api_key=None, host=None, ignore_time=False,
                 log_file=None, client=None, **kwargs):

        super().__init__(
            name="MCX_Momentum",
            symbol=symbol,
            quantity=quantity,
            interval="15m",
            exchange="MCX",
            api_key=api_key,
            host=host,
            ignore_time=ignore_time,
            log_file=log_file,
            client=client
        )

        # Strategy Parameters
        self.params = {
            'period_adx': 14,
            'period_rsi': 14,
            'period_atr': 14,
            'adx_threshold': 25,
            'min_atr': 10,
            'risk_per_trade': 0.02,
        }
        # Update with kwargs
        self.params.update(kwargs)

        self.logger.info(f"Initialized Strategy for {symbol}")
        self.logger.info(f"Filters: Seasonality={self.params.get('seasonality_score', 'N/A')}, "
                         f"USD_Vol={self.params.get('usd_inr_volatility', 'N/A')}")

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--underlying', type=str, help='Commodity Name (e.g., GOLD, SILVER)')
        parser.add_argument('--port', type=int, help='API Port (Override host)')
        # Custom Factors
        parser.add_argument('--usd_inr_trend', type=str, default='Neutral', help='USD/INR Trend')
        parser.add_argument('--usd_inr_volatility', type=float, default=0.0, help='USD/INR Volatility %%')
        parser.add_argument('--seasonality_score', type=int, default=50, help='Seasonality Score (0-100)')
        parser.add_argument('--global_alignment_score', type=int, default=50, help='Global Alignment Score')

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
        df = self.fetch_history(days=5, interval="15m")
        if df.empty or len(df) < 50:
            self.logger.warning(f"Insufficient data for {self.symbol}: {len(df)} rows. Need >50.")
            return

        # Calculate Indicators
        df['rsi'] = self.calculate_rsi(df['close'], period=self.params['period_rsi'])
        # ATR calc needs DataFrame
        # But BaseStrategy.calculate_atr returns scalar of last value.
        # We need series for logic? No, just last values usually.
        # But the original code calculated 'atr' column.
        # Let's use BaseStrategy utils directly if we need series.
        # BaseStrategy imports calculate_atr from trading_utils which returns Series.
        # But BaseStrategy.calculate_atr wrapper returns scalar.
        # So we can call self.calculate_atr(df) for scalar, or use internal import if needed.
        # Actually, let's just stick to scalar for decision or re-implement series calc if needed.
        # Original code: df['atr'] = calculate_atr(df, ...)
        # Let's import the function since BaseStrategy doesn't expose series version easily
        from trading_utils import calculate_atr, calculate_adx

        df['atr'] = calculate_atr(df, period=self.params['period_atr'])
        df['adx'] = calculate_adx(df, period=self.params['period_adx'])

        current = df.iloc[-1]
        prev = df.iloc[-2]

        # Multi-Factor Checks
        seasonality_ok = self.params.get('seasonality_score', 50) > 40
        global_alignment_ok = self.params.get('global_alignment_score', 50) >= 40
        usd_vol_high = self.params.get('usd_inr_volatility', 0) > 1.0

        # Adjust Position Size
        base_qty = self.quantity
        if usd_vol_high:
            self.logger.warning("⚠️ High USD/INR Volatility (>1.0%): Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7))

        has_position = self.pm.has_position() if self.pm else False

        if not seasonality_ok and not has_position:
            self.logger.info("Seasonality Weak: Skipping new entries.")
            return

        if not global_alignment_ok and not has_position:
            self.logger.info("Global Alignment Weak: Skipping new entries.")
            return

        # Entry Logic
        if not has_position:
            # BUY Signal
            if (current['adx'] > self.params['adx_threshold'] and
                current['rsi'] > 55 and
                current['close'] > prev['close']):

                self.logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                self.execute_trade('BUY', base_qty, current['close'])

            # SELL Signal
            elif (current['adx'] > self.params['adx_threshold'] and
                  current['rsi'] < 45 and
                  current['close'] < prev['close']):

                self.logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                self.execute_trade('SELL', base_qty, current['close'])

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position

            if pos_qty > 0: # Long
                if current['rsi'] < 45 or current['adx'] < 20:
                     self.logger.info(f"EXIT LONG: Trend Faded. RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                     self.execute_trade('SELL', abs(pos_qty), current['close'])
            elif pos_qty < 0: # Short
                if current['rsi'] > 55 or current['adx'] < 20:
                     self.logger.info(f"EXIT SHORT: Trend Faded. RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                     self.execute_trade('BUY', abs(pos_qty), current['close'])

    def generate_signal(self, df):
        """
        Generate signal for backtesting (Legacy Support)
        """
        if df.empty: return 'HOLD', 0.0, {}

        # Re-calc indicators locally for backtest df
        from trading_utils import calculate_atr, calculate_adx, calculate_rsi
        df = df.copy()
        df['rsi'] = calculate_rsi(df['close'], period=self.params['period_rsi'])
        df['atr'] = calculate_atr(df, period=self.params['period_atr'])
        df['adx'] = calculate_adx(df, period=self.params['period_adx'])

        current = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else current

        seasonality_ok = self.params.get('seasonality_score', 50) > 40
        if not seasonality_ok:
            return 'HOLD', 0.0, {'reason': 'Seasonality Weak'}

        action = 'HOLD'
        if (current['adx'] > self.params['adx_threshold'] and
            current['rsi'] > 50 and
            current['close'] > prev['close']):
            action = 'BUY'
        elif (current['adx'] > self.params['adx_threshold'] and
              current['rsi'] < 50 and
              current['close'] < prev['close']):
            action = 'SELL'

        return action, 1.0, {'atr': current.get('atr', 0)}

# Module level wrapper for SimpleBacktestEngine
def generate_signal(df, client=None, symbol=None, params=None):
    # Default params
    strat_params = {
        'period_adx': 14,
        'period_rsi': 14,
        'period_atr': 14,
        'adx_threshold': 25,
        'min_atr': 10,
        'risk_per_trade': 0.02,
    }
    if params:
        strat_params.update(params)

    api_key = client.api_key if client and hasattr(client, 'api_key') else "BACKTEST"
    host = client.host if client and hasattr(client, 'host') else "http://127.0.0.1:5001"

    # Instantiate strategy
    strat = MCXMomentumStrategy(symbol=symbol or "TEST", quantity=1, api_key=api_key, host=host, client=client, **strat_params)
    strat.logger.handlers = [] # Silence logger during backtest
    strat.logger.addHandler(logging.NullHandler())

    # Set Time Stop for Engine
    setattr(strat, 'TIME_STOP_BARS', 12)

    return strat.generate_signal(df)

if __name__ == "__main__":
    MCXMomentumStrategy.cli()
