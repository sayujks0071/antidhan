"""Adapter for SuperTrend VWAP strategy"""
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

# Add paths
_script_dir = os.path.dirname(os.path.abspath(__file__))
_strategies_dir = os.path.dirname(_script_dir)
_utils_dir = os.path.join(_strategies_dir, 'utils')
_scripts_dir = os.path.join(_strategies_dir, 'scripts')

sys.path.insert(0, _strategies_dir)
sys.path.insert(0, _utils_dir)
sys.path.insert(0, _scripts_dir)

from strategy_adapter import StrategyAdapter
from aitrapp_integration import StrategyContext, Signal, SignalSide, Instrument, InstrumentType
from openalgo_mock import get_mock

class SuperTrendVWAPAdapter(StrategyAdapter):
    """Adapter for SuperTrend VWAP strategy"""

    def __init__(self, name: str = "SuperTrend VWAP", params: dict = None):
        strategy_path = os.path.join(
            _scripts_dir,
            'supertrend_vwap_strategy.py'
        )
        params = params or {}
        super().__init__(name, params, strategy_path)

        # Risk management parameters (defaults if not in params)
        self.stop_loss_pct = params.get('stop_loss_pct', 0.10) # 10% SL on Option
        self.take_profit_pct = params.get('take_profit_pct', 0.20) # 20% TP on Option
        self.risk_per_trade = params.get('risk_per_trade', 10000) # Risk amount

    def _extract_signals(self, context: StrategyContext):
        """Extract signals from strategy logic"""
        signals = []
        mock = get_mock()
        if not mock:
            return signals

        # Market Hours Check (simplified)
        now = context.timestamp
        if now.hour < 9 or (now.hour == 9 and now.minute < 15) or now.hour >= 15:
             return signals

        # Get historical data (underlying NIFTY or BANKNIFTY)
        symbol = context.instrument.symbol # e.g. NIFTY

        # Get last 5 days for Volume Profile
        start_date = (context.timestamp - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = context.timestamp.strftime("%Y-%m-%d")

        # Use mock history
        data = mock.post_json("history", {
            "symbol": symbol, # Underlying
            "exchange": "NSE",
            "interval": "5m",
            "start_date": start_date,
            "end_date": end_date,
        })

        if data.get("status") != "success" or not data.get("data"):
            return signals

        df = pd.DataFrame(data["data"])
        if df.empty:
            return signals

        # Ensure numeric
        cols = ['open', 'high', 'low', 'close', 'volume']
        for c in cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c])

        if 'close' not in df.columns or 'volume' not in df.columns:
             return signals

        # Calculate VWAP
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3
        df['pv'] = df['tp'] * df['volume']
        df['cum_pv'] = df['pv'].cumsum()
        df['cum_vol'] = df['volume'].cumsum()
        df['vwap'] = df['cum_pv'] / df['cum_vol']
        df['vwap_dev'] = (df['close'] - df['vwap']) / df['vwap']

        # Volume Profile Analysis
        # Just use the last day for profile to match strategy intent (or full 5 days?)
        # Strategy says "Fetch sufficient history... (last 5 days)".
        price_min = df['low'].min()
        price_max = df['high'].max()
        bins = np.linspace(price_min, price_max, 20)
        df['bin'] = pd.cut(df['close'], bins=bins, labels=False)
        volume_profile = df.groupby('bin')['volume'].sum()
        if volume_profile.empty:
            return signals
        poc_bin = volume_profile.idxmax()
        if pd.isna(poc_bin):
            return signals
        poc_price = bins[int(poc_bin)] + (bins[1] - bins[0]) / 2

        # Last bar
        last = df.iloc[-1]

        # Conditions
        is_above_vwap = last['close'] > last['vwap']
        is_volume_spike = last['volume'] > df['volume'].mean() * 1.5
        is_above_poc = last['close'] > poc_price
        is_not_overextended = abs(last['vwap_dev']) < 0.02

        if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended:
            # Generate BUY Signal
            # Only if context.instrument is a CE (Call)
            if context.instrument.instrument_type == InstrumentType.CE:

                # Create Signal
                # Price is Option Price (LTP)
                option_price = context.latest_tick.last_price if context.latest_tick else 0
                if option_price <= 0:
                    return signals

                stop_loss = option_price * (1 - self.stop_loss_pct)
                take_profit = option_price * (1 + self.take_profit_pct)

                signal = self._create_signal(
                    instrument=context.instrument,
                    side=SignalSide.LONG,
                    entry_price=option_price,
                    stop_loss=stop_loss,
                    take_profit_1=take_profit,
                    take_profit_2=take_profit * 1.5,
                    confidence=0.8,
                    rationale=f"VWAP Crossover: Price {last['close']} > VWAP {last['vwap']:.2f}, POC {poc_price:.2f}"
                )
                signals.append(signal)

        return signals
