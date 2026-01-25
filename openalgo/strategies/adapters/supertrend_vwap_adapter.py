"""Adapter for SuperTrend VWAP Strategy"""
import os
import sys
from datetime import datetime, timedelta
from typing import List, Optional
import pandas as pd
import numpy as np

# Add paths
_script_dir = os.path.dirname(os.path.abspath(__file__))
_strategies_dir = os.path.dirname(_script_dir)
_utils_dir = os.path.join(_strategies_dir, 'utils')
_scripts_dir = os.path.join(_strategies_dir, 'scripts')

if _strategies_dir not in sys.path:
    sys.path.insert(0, _strategies_dir)
if _utils_dir not in sys.path:
    sys.path.insert(0, _utils_dir)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from strategy_adapter import StrategyAdapter
from aitrapp_integration import StrategyContext, Signal, SignalSide, Instrument, InstrumentType
from openalgo_mock import get_mock
from trading_utils import calculate_intraday_vwap

class SuperTrendVWAPAdapter(StrategyAdapter):
    """Adapter for SuperTrend VWAP strategy for Backtesting"""

    def __init__(self, name: str = "SuperTrend VWAP", params: dict = None):
        strategy_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts',
            'supertrend_vwap_strategy.py'
        )
        params = params or {}
        super().__init__(name, params, strategy_path)

        # Strategy Parameters
        self.symbol = params.get('symbol', 'NIFTY')
        self.quantity = params.get('quantity', 50) # 1 Lot

        # State
        self.last_trade_date = None

    def _reset_state(self):
        self.last_trade_date = None

    def analyze_volume_profile(self, df, n_bins=20):
        """
        Basic Volume Profile analysis.
        Identify Point of Control (POC) - price level with highest volume.
        """
        if df.empty:
            return 0, 0

        price_min = df['low'].min()
        price_max = df['high'].max()

        if price_min == price_max:
             return price_min, df['volume'].sum()

        # Create bins
        bins = np.linspace(price_min, price_max, n_bins)

        # Bucket volume into price bins
        # Using 'close' as proxy for trade price in the bin
        df_copy = df.copy()
        df_copy['bin'] = pd.cut(df_copy['close'], bins=bins, labels=False)

        volume_profile = df_copy.groupby('bin')['volume'].sum()

        # Find POC Bin
        if volume_profile.empty:
            return 0, 0

        poc_bin = volume_profile.idxmax()
        poc_volume = volume_profile.max()

        # Approximate POC Price (midpoint of bin)
        if pd.isna(poc_bin):
            return 0, 0

        poc_bin = int(poc_bin)
        # Check bounds
        if poc_bin >= len(bins) - 1:
             poc_bin = len(bins) - 2

        poc_price = bins[poc_bin] + (bins[poc_bin+1] - bins[poc_bin]) / 2

        return poc_price, poc_volume

    def calculate_supertrend(self, df, period=10, multiplier=3.0):
        """Calculate SuperTrend Indicator"""
        high = df['high']
        low = df['low']
        close = df['close']

        # ATR Calculation
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/period, adjust=False).mean()

        # Basic Bands
        hl2 = (high + low) / 2
        final_upperband = hl2 + (multiplier * atr)
        final_lowerband = hl2 - (multiplier * atr)

        supertrend = [True] * len(df) # True = Green/Long, False = Red/Short

        # Iterative calculation
        for i in range(1, len(df)):
            curr_close = close.iloc[i]
            prev_close = close.iloc[i-1]

            # Upper Band Logic
            if curr_close > final_upperband.iloc[i-1]:
                final_upperband.iloc[i] = max(final_upperband.iloc[i], final_upperband.iloc[i-1]) # Should check condition
            else:
                 final_upperband.iloc[i] = final_upperband.iloc[i]

            # Simple recursive implementation usually requires checking trend state
            # Using a simplified pandas approach for readability and robustness
            pass # Placeholder, doing full loop below

        # Optimized loop
        supertrend = np.zeros(len(df))
        final_upper = np.zeros(len(df))
        final_lower = np.zeros(len(df))

        # Initialize
        final_upper[0] = final_upperband.iloc[0]
        final_lower[0] = final_lowerband.iloc[0]

        trend = True # Assume Up

        for i in range(1, len(df)):
            prev_upper = final_upper[i-1]
            prev_lower = final_lower[i-1]
            curr_close = close.iloc[i]
            prev_close = close.iloc[i-1]

            # Upper Band
            if final_upperband.iloc[i] < prev_upper or prev_close > prev_upper:
                final_upper[i] = final_upperband.iloc[i]
            else:
                final_upper[i] = prev_upper

            # Lower Band
            if final_lowerband.iloc[i] > prev_lower or prev_close < prev_lower:
                final_lower[i] = final_lowerband.iloc[i]
            else:
                final_lower[i] = prev_lower

            # Trend
            if trend:
                if curr_close < final_lower[i]:
                    trend = False
            else:
                if curr_close > final_upper[i]:
                    trend = True

            supertrend[i] = 1 if trend else -1

        df['supertrend'] = supertrend
        return df

    def _extract_signals(self, context: StrategyContext) -> List[Signal]:
        signals = []
        mock = get_mock()
        if not mock:
            return signals

        # 1. Get Historical Data (Last 5 days for Volume Profile and Indicators)
        end_date = context.timestamp
        start_date = end_date - timedelta(days=5)

        # Fetch NIFTY Spot data
        data_resp = mock.post_json("history", {
            "symbol": self.symbol,
            "exchange": "NSE",
            "interval": "5m",
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        })

        if data_resp.get("status") != "success" or not data_resp.get("data"):
            return signals

        df = pd.DataFrame(data_resp["data"])
        if df.empty:
            return signals

        if 'time' in df.columns:
            df['datetime'] = pd.to_datetime(df['time'])
            df = df.set_index('datetime')

        # 2. Calculate Indicators
        # Intraday VWAP
        df = calculate_intraday_vwap(df)

        # SuperTrend
        df = self.calculate_supertrend(df, period=10, multiplier=3)

        last = df.iloc[-1]

        # Check if we are at the latest timestamp (approx)
        if (context.timestamp - last.name).total_seconds() > 300: # 5 mins
             return signals

        # Volume Profile
        poc_price, poc_vol = self.analyze_volume_profile(df)

        # 3. Strategy Logic
        # Price > VWAP
        is_above_vwap = last['close'] > last['vwap']
        # Volume Spike (> 1.5x Avg)
        avg_vol = df['volume'].mean()
        is_volume_spike = last['volume'] > avg_vol * 1.5
        # Price > POC
        is_above_poc = last['close'] > poc_price
        # VWAP Deviation
        is_not_overextended = abs(last['vwap_dev']) < 0.02
        # SuperTrend Bullish
        is_supertrend_bullish = last['supertrend'] == 1

        # Signal Generation
        if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and is_supertrend_bullish:

            # Select ATM Call Option to Buy
            strike_info = self._get_atm_call_option(mock, self.symbol, last['close'])
            if not strike_info:
                return signals

            instrument = Instrument(
                token=hash(strike_info['symbol']) % (2**31), # Mock token
                symbol=self.symbol,
                tradingsymbol=strike_info['symbol'],
                exchange="NFO",
                instrument_type=InstrumentType.CE,
                strike=strike_info['strike'],
                lot_size=50 if self.symbol == "NIFTY" else 25,
                tick_size=0.05
            )

            # Risk Management (Example)
            entry_price = strike_info['ltp']
            stop_loss = entry_price * 0.90 # 10% SL
            take_profit = entry_price * 1.20 # 20% Target

            signal = self._create_signal(
                instrument=instrument,
                side=SignalSide.LONG,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit_1=take_profit,
                confidence=0.8,
                rationale=f"VWAP+SuperTrend: Price={last['close']:.2f}, ST=Bullish, POC={poc_price:.2f}"
            )
            signals.append(signal)

        return signals

    def _get_atm_call_option(self, mock, symbol, spot_price):
        """Find nearest ATM Call Option"""
        # Get Expiry
        expiry_resp = mock.post_json("expiry", {"symbol": symbol, "exchange": "NFO"})
        expiries = expiry_resp.get("data", [])
        if not expiries:
            return None
        expiry = expiries[0].replace("-", "") # First expiry

        # Get Option Chain to find ATM
        chain_resp = mock.post_json("optionchain", {
            "underlying": symbol,
            "exchange": "NSE", # Underlying exchange
            "expiry_date": expiry,
            "strike_count": 10
        })

        if chain_resp.get("status") != "success":
            return None

        chain = chain_resp.get("chain", [])
        if not chain:
            return None

        # Find closest strike to spot_price
        best_strike = None
        min_diff = float('inf')

        for item in chain:
            strike = item['strike']
            diff = abs(strike - spot_price)
            if diff < min_diff:
                min_diff = diff
                best_strike = item

        if best_strike and 'ce' in best_strike:
            data = best_strike['ce']
            return {
                'symbol': data['symbol'],
                'strike': best_strike['strike'],
                'ltp': data['ltp']
            }
        return None
