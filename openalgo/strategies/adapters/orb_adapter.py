"""Adapter for ORB Strategy"""
import os
import sys
from datetime import datetime, time, timedelta
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

class ORBAdapter(StrategyAdapter):
    """Adapter for ORB Strategy for Backtesting"""

    def __init__(self, name: str = "ORB Strategy", params: dict = None):
        strategy_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts',
            'orb_strategy.py'
        )
        params = params or {}
        super().__init__(name, params, strategy_path)

        # Strategy Parameters
        self.symbol = params.get('symbol', 'NIFTY')
        self.quantity = params.get('quantity', 50)
        self.orb_start_time = time(9, 15)
        self.orb_end_time = time(9, 30)

        # State (reset daily)
        self.current_date = None
        self.orb_high = None
        self.orb_low = None
        self.orb_vol_avg = None
        self.has_traded_today = False

    def _reset_daily_state(self, current_date):
        self.current_date = current_date
        self.orb_high = None
        self.orb_low = None
        self.orb_vol_avg = None
        self.has_traded_today = False

    def _extract_signals(self, context: StrategyContext) -> List[Signal]:
        signals = []
        mock = get_mock()
        if not mock:
            return signals

        timestamp = context.timestamp
        current_date = timestamp.date()
        current_time = timestamp.time()

        # Reset state if new day
        if self.current_date != current_date:
            self._reset_daily_state(current_date)

        # 1. Wait for ORB period to end
        if current_time <= self.orb_end_time:
            return signals

        # 2. Calculate ORB levels if not set
        if self.orb_high is None:
            # Fetch data for 9:15 to 9:30
            start_dt = datetime.combine(current_date, self.orb_start_time)
            end_dt = datetime.combine(current_date, self.orb_end_time)

            # Using history endpoint
            # Note: In backtesting, we might need to fetch a slightly wider range or ensuring specific candles
            # Mocks usually return what is requested.
            data_resp = mock.post_json("history", {
                "symbol": self.symbol,
                "exchange": "NSE",
                "interval": "1m",
                "start_date": current_date.strftime("%Y-%m-%d"),
                "end_date": current_date.strftime("%Y-%m-%d"),
            })

            if data_resp.get("status") != "success" or not data_resp.get("data"):
                return signals

            df = pd.DataFrame(data_resp["data"])
            if df.empty:
                return signals

            if 'time' in df.columns:
                df['datetime'] = pd.to_datetime(df['time'])
                df = df.set_index('datetime')

            # Filter for ORB period
            mask = (df.index.time >= self.orb_start_time) & (df.index.time < self.orb_end_time)
            orb_df = df[mask]

            if orb_df.empty:
                return signals

            self.orb_high = orb_df['high'].max()
            self.orb_low = orb_df['low'].min()
            self.orb_vol_avg = orb_df['volume'].mean()

        # 3. Check for Breakout
        if self.has_traded_today:
            return signals

        # Get latest candle
        # We assume context.bar is available or fetch latest
        # In this adapter structure, we usually fetch latest history
        data_resp = mock.post_json("history", {
            "symbol": self.symbol,
            "exchange": "NSE",
            "interval": "1m", # Checking 1m breakout
            "start_date": current_date.strftime("%Y-%m-%d"),
            "end_date": current_date.strftime("%Y-%m-%d"),
        })

        if data_resp.get("status") != "success":
            return signals

        df = pd.DataFrame(data_resp["data"])
        if df.empty: return signals

        if 'time' in df.columns:
            df['datetime'] = pd.to_datetime(df['time'])
            df = df.set_index('datetime')

        # Get the candle at (or just before) current timestamp
        try:
            # simple lookup or nearest
            # assuming df index is sorted
            current_idx = df.index.get_indexer([timestamp], method='pad')[0]
            if current_idx == -1: return signals
            last = df.iloc[current_idx]

            # Ensure it's recent (within 5 mins)
            if (timestamp - last.name).total_seconds() > 300:
                return signals

        except:
            return signals

        # Logic
        signal_side = None
        rationale = ""

        if last['close'] > self.orb_high and last['volume'] > self.orb_vol_avg:
            signal_side = SignalSide.LONG
            rationale = f"ORB Breakout UP: Price {last['close']} > {self.orb_high}, Vol > Avg"
        elif last['close'] < self.orb_low and last['volume'] > self.orb_vol_avg:
            signal_side = SignalSide.SHORT
            rationale = f"ORB Breakout DOWN: Price {last['close']} < {self.orb_low}, Vol > Avg"

        if signal_side:
            self.has_traded_today = True # One trade per day

            # Create Signal
            # For NIFTY, we might trade Options (ATM)
            # Find ATM Option
            strike_info = self._get_atm_option(mock, self.symbol, last['close'], 'CE' if signal_side == SignalSide.LONG else 'PE')

            if not strike_info:
                return signals

            instrument = Instrument(
                token=hash(strike_info['symbol']) % (2**31),
                symbol=self.symbol,
                tradingsymbol=strike_info['symbol'],
                exchange="NFO",
                instrument_type=InstrumentType.CE if signal_side == SignalSide.LONG else InstrumentType.PE,
                strike=strike_info['strike'],
                lot_size=50 if self.symbol == "NIFTY" else 25,
                tick_size=0.05
            )

            entry_price = strike_info['ltp']
            # Simple Risk Management
            stop_loss = entry_price * 0.90
            take_profit = entry_price * 1.30

            signal = self._create_signal(
                instrument=instrument,
                side=SignalSide.LONG, # Always Buy Options
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit_1=take_profit,
                confidence=1.0,
                rationale=rationale
            )
            signals.append(signal)

        return signals

    def _get_atm_option(self, mock, symbol, spot_price, option_type):
        """Find nearest ATM Option"""
        # Get Expiry
        expiry_resp = mock.post_json("expiry", {"symbol": symbol, "exchange": "NFO"})
        expiries = expiry_resp.get("data", [])
        if not expiries:
            return None
        expiry = expiries[0].replace("-", "")

        # Get Option Chain
        chain_resp = mock.post_json("optionchain", {
            "underlying": symbol,
            "exchange": "NSE",
            "expiry_date": expiry,
            "strike_count": 10
        })

        if chain_resp.get("status") != "success": return None
        chain = chain_resp.get("chain", [])
        if not chain: return None

        # Find closest strike
        best_strike = None
        min_diff = float('inf')

        for item in chain:
            strike = item['strike']
            diff = abs(strike - spot_price)
            if diff < min_diff:
                min_diff = diff
                best_strike = item

        key = option_type.lower()
        if best_strike and key in best_strike:
            data = best_strike[key]
            return {
                'symbol': data['symbol'],
                'strike': best_strike['strike'],
                'ltp': data['ltp']
            }
        return None
