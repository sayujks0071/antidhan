#!/usr/bin/env python3
"""
AI Hybrid Reversion Breakout Strategy
Refactored to use BaseStrategy.
"""
import os
import sys
import logging
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
try:
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy
    from trading_utils import normalize_symbol

class AIHybridStrategy(BaseStrategy):
    def __init__(self, symbol, quantity=10, api_key=None, host=None, rsi_lower=30, rsi_upper=60, stop_pct=1.0, sector='NIFTY 50', earnings_date=None, time_stop_bars=12, **kwargs):
        super().__init__(
            name=f"AIHybrid_{symbol}",
            symbol=symbol,
            quantity=quantity,
            api_key=api_key,
            host=host,
            **kwargs
        )
        self.rsi_lower = rsi_lower
        self.rsi_upper = rsi_upper
        self.stop_pct = stop_pct
        self.sector = sector
        self.earnings_date = earnings_date
        self.time_stop_bars = time_stop_bars

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--rsi_lower', type=float, default=35.0, help='RSI Lower Threshold')
        parser.add_argument('--rsi_upper', type=float, default=60.0, help='RSI Upper Threshold')
        parser.add_argument('--stop_pct', type=float, default=1.0, help='Stop Loss %%')
        parser.add_argument('--earnings_date', type=str, help='Earnings Date YYYY-MM-DD')
        # sector is already in BaseStrategy

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        if hasattr(args, 'rsi_lower') and args.rsi_lower: kwargs['rsi_lower'] = args.rsi_lower
        if hasattr(args, 'rsi_upper') and args.rsi_upper: kwargs['rsi_upper'] = args.rsi_upper
        if hasattr(args, 'stop_pct') and args.stop_pct: kwargs['stop_pct'] = args.stop_pct
        if hasattr(args, 'earnings_date') and args.earnings_date: kwargs['earnings_date'] = args.earnings_date
        return kwargs

    def cycle(self):
        # Earnings Filter
        if self.check_earnings():
            self.logger.info("Earnings approaching (<2 days). Skipping trades.")
            return

        context = self.get_market_context()

        # VIX Sizing
        size_multiplier = 1.0
        if context['vix'] > 25:
            size_multiplier = 0.5
            self.logger.info(f"High VIX ({context['vix']}). Reducing size by 50%.")

        # Market Breadth Filter
        if context['breadth_ad_ratio'] < 0.7:
             self.logger.info("Weak Market Breadth. Skipping long entries.")
             return

        # Sector Rotation Filter
        if not self.check_sector_strength():
            self.logger.info(f"Sector {self.sector} Weak. Skipping.")
            return

        # Adaptive Sizing
        monthly_atr = self.get_monthly_atr()
        base_qty = self.quantity # Default from init

        # Override default 100 with adaptive
        if monthly_atr > 0 and self.pm:
            # 1% Risk on 500k Capital
            quote = self.client.get_quote(self.symbol, self.exchange)
            ltp = quote.get('ltp', 0) if quote else 0
            if ltp > 0:
                adaptive_qty = self.pm.calculate_risk_adjusted_quantity(500000, 1.0, monthly_atr, ltp)
                if adaptive_qty > 0:
                    base_qty = adaptive_qty
                    self.logger.info(f"Adaptive Base Qty: {base_qty} (Monthly ATR: {monthly_atr:.2f})")
        else:
            base_qty = 100 # Fallback default

        # Fetch Data
        exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"
        df = self.fetch_history(days=30, interval="5m", exchange=exchange)

        if df.empty or len(df) < 20:
            return

        # Indicators
        df['rsi'] = self.calculate_rsi(df['close'])
        df['sma20'], df['upper'], df['lower'] = self.calculate_bollinger_bands(df['close'])

        last = df.iloc[-1]
        current_price = last['close']

        # Manage Position
        if self.pm and self.pm.has_position():
            pnl = self.pm.get_pnl(current_price)
            entry = self.pm.entry_price

            if (self.pm.position > 0 and current_price < entry * (1 - self.stop_pct/100)) or \
               (self.pm.position < 0 and current_price > entry * (1 + self.stop_pct/100)):
                self.logger.info(f"Stop Loss Hit. PnL: {pnl}")
                self.execute_trade('SELL' if self.pm.position > 0 else 'BUY', abs(self.pm.position), current_price)

            elif (self.pm.position > 0 and current_price > last['sma20']):
                self.logger.info(f"Reversion Target Hit (SMA20). PnL: {pnl}")
                self.execute_trade('SELL', abs(self.pm.position), current_price)

            return

        # Reversion Logic
        if last['rsi'] < self.rsi_lower and last['close'] < last['lower']:
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > avg_vol * 1.2:
                qty = int(base_qty * size_multiplier)
                if qty < 1: qty = 1
                self.logger.info(f"Oversold Reversion Signal. Qty: {qty}")
                self.execute_trade('BUY', qty, current_price)

        # Breakout Logic
        elif last['rsi'] > self.rsi_upper and last['close'] > last['upper']:
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > avg_vol * 2.0:
                 qty = int(base_qty * size_multiplier)
                 if qty < 1: qty = 1
                 self.logger.info(f"Breakout Signal. Qty: {qty}")
                 self.execute_trade('BUY', qty, current_price)


    def get_market_context(self):
        vix = self.get_vix() # BaseStrategy has get_vix
        if not vix: vix = 15.0 # Fallback in case BaseStrategy returns None

        # Fetch Breadth
        breadth = 1.2
        try:
            nifty = self.fetch_history(days=5, symbol="NIFTY 50", exchange="NSE_INDEX", interval="1d")
            if not nifty.empty and nifty['close'].iloc[-1] > nifty['open'].iloc[-1]:
                breadth = 1.5
            elif not nifty.empty:
                breadth = 0.8
        except:
            pass

        return {'vix': vix, 'breadth_ad_ratio': breadth}

    def check_earnings(self):
        if not self.earnings_date: return False
        try:
            e_date = None
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
                try:
                    e_date = datetime.strptime(self.earnings_date, fmt)
                    break
                except ValueError: continue
            if not e_date: return False
            days_diff = (e_date - datetime.now()).days
            if 0 <= days_diff <= 2: return True
        except: pass
        return False

    def check_sector_strength(self):
        try:
            sector_symbol = normalize_symbol(self.sector)
            exchange = "NSE_INDEX" if "NIFTY" in sector_symbol.upper() else "NSE"
            df = self.fetch_history(days=60, symbol=sector_symbol, interval="D", exchange=exchange)

            if df.empty or len(df) < 20: return True

            # Using manual rolling here as calculate_sma helper handles Series
            df['sma20'] = df['close'].rolling(20).mean()
            last_close = df.iloc[-1]['close']
            last_sma20 = df.iloc[-1]['sma20']
            if pd.isna(last_sma20): return True

            return last_close > last_sma20
        except Exception as e:
            self.logger.warning(f"Error checking sector strength: {e}")
            return True

    def calculate_signal(self, df):
        """Calculate signal for a given dataframe (Backtesting support)."""
        if df.empty or len(df) < 20:
            return 'HOLD', 0.0, {}

        # Indicators
        df['rsi'] = self.calculate_rsi(df['close'])
        df['sma20'], df['upper'], df['lower'] = self.calculate_bollinger_bands(df['close'])

        # Regime Filter (SMA200)
        df['sma200'] = df['close'].rolling(200).mean()

        last = df.iloc[-1]

        # Volatility Sizing
        atr = self.calculate_atr(df)

        risk_amount = 1000.0

        if atr > 0:
            qty = int(risk_amount / (2.0 * atr))
            qty = max(1, min(qty, 500))
        else:
            qty = 50

        # Check Regime
        is_bullish_regime = True
        if not pd.isna(last.get('sma200')) and last['close'] < last['sma200']:
            is_bullish_regime = False

        # Reversion Logic
        if last['rsi'] < self.rsi_lower and last['close'] < last['lower']:
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > avg_vol * 1.2:
                return 'BUY', 1.0, {'type': 'REVERSION', 'rsi': last['rsi'], 'close': last['close'], 'quantity': qty}

        # Breakout Logic
        elif last['rsi'] > self.rsi_upper and last['close'] > last['upper']:
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > avg_vol * 2.0 and is_bullish_regime:
                 return 'BUY', 1.0, {'type': 'BREAKOUT', 'rsi': last['rsi'], 'close': last['close'], 'quantity': qty}

        return 'HOLD', 0.0, {}

def run_strategy():
    AIHybridStrategy.cli()

# Module level wrapper for SimpleBacktestEngine
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'rsi_lower': 30.0,
        'rsi_upper': 60.0,
        'stop_pct': 1.0,
        'sector': 'NIFTY 50'
    }
    if params:
        strat_params.update(params)

    strat = AIHybridStrategy(
        symbol=symbol or "TEST",
        quantity=10,
        api_key="dummy",
        host="http://127.0.0.1:5001",
        rsi_lower=float(strat_params.get('rsi_lower', 30.0)),
        rsi_upper=float(strat_params.get('rsi_upper', 60.0)),
        stop_pct=float(strat_params.get('stop_pct', 1.0)),
        sector=strat_params.get('sector', 'NIFTY 50')
    )

    # Silence logger for backtest
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    global TIME_STOP_BARS
    TIME_STOP_BARS = getattr(strat, 'time_stop_bars', 12)

    return strat.calculate_signal(df)

# Global default for engine check
TIME_STOP_BARS = 12

if __name__ == "__main__":
    run_strategy()
