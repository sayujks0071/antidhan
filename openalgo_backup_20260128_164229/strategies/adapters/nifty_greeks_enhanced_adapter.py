"""Adapter for nifty_greeks_enhanced_20260122.py strategy"""
import os
import sys
from datetime import datetime
from typing import List, Optional
import pandas as pd
import numpy as np

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
from aitrapp_utils import OptimizedIndicators, PositionSizer, PortfolioHeatTracker

# Import strategy constants and functions
from nifty_greeks_enhanced_20260122 import (
    UNDERLYING, UNDERLYING_EXCHANGE, OPTIONS_EXCHANGE, STRIKE_INT,
    ACCOUNT_SIZE, RISK_PCT, MAX_POSITIONS, DAILY_LOSS_LIMIT_PCT,
    EMA_FAST, EMA_SLOW, ADX_PERIOD, ATR_PERIOD, RSI_PERIOD,
    MIN_ADX, MIN_ATR_PCT, MAX_ATR_PCT,
    RSI_LONG_MIN, RSI_LONG_MAX, RSI_SHORT_MIN, RSI_SHORT_MAX,
    VWAP_MIN_DIST, MIN_DELTA, MAX_DELTA, MAX_THETA_PER_HOUR,
    IV_RANK_MIN, IV_RANK_MAX, SL_PCT, TP1_PCT, TP2_PCT,
    SKIP_FIRST_MINUTES, SKIP_LAST_MINUTES
)


class NiftyGreeksEnhancedAdapter(StrategyAdapter):
    """Adapter for NIFTY Greeks Enhanced strategy"""
    
    def __init__(self, name: str = "NIFTY Greeks Enhanced", params: dict = None):
        strategy_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts',
            'nifty_greeks_enhanced_20260122.py'
        )
        params = params or {}
        super().__init__(name, params, strategy_path)
        
        # Strategy Parameters with Defaults
        self.delta_min = params.get('delta_min', MIN_DELTA)
        self.delta_max = params.get('delta_max', MAX_DELTA)
        self.iv_rank_min = params.get('iv_rank_min', IV_RANK_MIN)
        self.iv_rank_max = params.get('iv_rank_max', IV_RANK_MAX)
        self.min_adx = params.get('min_adx', MIN_ADX)
        self.rsi_period = params.get('rsi_period', RSI_PERIOD)

        # Initialize heat tracker
        self.heat_tracker = PortfolioHeatTracker(ACCOUNT_SIZE, max_heat_pct=2.0)
        self.daily_pnl = 0.0
        
    def _reset_state(self):
        """Reset state for new backtest"""
        self.heat_tracker = PortfolioHeatTracker(ACCOUNT_SIZE, max_heat_pct=2.0)
        self.daily_pnl = 0.0
    
    def _extract_signals(self, context: StrategyContext) -> List[Signal]:
        """Extract signals from strategy logic"""
        signals = []
        mock = get_mock()
        if not mock:
            return signals
        
        # Check market time
        now = context.timestamp
        if not self._market_time_ok(now):
            return signals
        
        # Check daily loss limit
        if self.daily_pnl <= -(ACCOUNT_SIZE * DAILY_LOSS_LIMIT_PCT / 100):
            return signals
        
        # Get historical data
        df = self._get_history(context)
        if df is None or df.empty or len(df) < max(EMA_SLOW, ADX_PERIOD, ATR_PERIOD, RSI_PERIOD):
            return signals
        
        # Calculate indicators
        price = df["close"].iloc[-1]
        ema_fast = self._ema(df["close"], EMA_FAST).iloc[-1]
        ema_slow = self._ema(df["close"], EMA_SLOW).iloc[-1]
        current_adx = self._adx(df, ADX_PERIOD).iloc[-1]
        current_atr = self._atr(df, ATR_PERIOD).iloc[-1]
        current_rsi = self._rsi(df, RSI_PERIOD).iloc[-1]
        current_vwap = self._vwap(df).iloc[-1]
        
        atr_pct = current_atr / price if price > 0 else 0
        vwap_dist = (price - current_vwap) / current_vwap if current_vwap > 0 else 0
        
        # Basic filters
        if current_adx < self.min_adx:
            return signals
        if atr_pct < MIN_ATR_PCT or atr_pct > MAX_ATR_PCT:
            return signals
        
        # Determine direction
        direction = None
        momentum_score = 0
        
        # Use RSI from indicators but we rely on hardcoded thresholds from imports for now
        # unless we override them too. For minimal change, we keep constants but using self.rsi_period above

        if ema_fast > ema_slow and RSI_LONG_MIN <= current_rsi <= RSI_LONG_MAX and vwap_dist >= VWAP_MIN_DIST:
            direction = "LONG"
            momentum_score = min(100, (current_adx / 50) * 50 + (current_rsi - 50) * 0.5)
        elif ema_fast < ema_slow and RSI_SHORT_MIN <= current_rsi <= RSI_SHORT_MAX and vwap_dist <= -VWAP_MIN_DIST:
            direction = "SHORT"
            momentum_score = min(100, (current_adx / 50) * 50 + (50 - current_rsi) * 0.5)
        
        if not direction:
            return signals
        
        # Get expiry
        expiry = self._get_nearest_expiry(mock)
        if not expiry:
            return signals
        
        option_type = "CE" if direction == "LONG" else "PE"
        
        # Select delta target based on momentum
        if momentum_score >= 70:
            delta_min, delta_max = 0.6, 0.8
        elif momentum_score >= 40:
            delta_min, delta_max = 0.4, 0.6
        else:
            delta_min, delta_max = 0.2, 0.4
        
        # Select strike
        strike_info = self._select_strike_by_delta(mock, expiry, option_type, delta_min, delta_max)
        if not strike_info:
            return signals
        
        # Check IV Rank (simplified)
        iv_rank = self._calculate_iv_rank_simple(strike_info.get('iv', 0.15))
        if iv_rank < self.iv_rank_min or iv_rank > self.iv_rank_max:
            return signals
        
        # Check delta
        delta = strike_info.get('delta', 0)
        if delta < self.delta_min or delta > self.delta_max:
            return signals
        
        # Check theta
        theta = strike_info.get('theta', 0)
        theta_per_hour = theta / 6.5
        if abs(theta_per_hour) > abs(MAX_THETA_PER_HOUR):
            return signals
        
        # Get premium
        premium = strike_info.get('ltp', 0)
        if premium <= 0:
            return signals
        
        # Check portfolio heat
        stop_distance = premium * SL_PCT
        risk_amount = stop_distance * strike_info.get('lotsize', 50)
        can_take, _ = self.heat_tracker.can_take_new_position(risk_amount)
        if not can_take:
            return signals
        
        # Create instrument
        strike = strike_info.get('strike', 0)
        instrument = Instrument(
            token=hash(f"{UNDERLYING}{strike}{option_type}") % (2**31),
            symbol=UNDERLYING,
            tradingsymbol=strike_info.get('symbol', f"{UNDERLYING}{int(strike)}{option_type}"),
            exchange=OPTIONS_EXCHANGE,
            instrument_type=InstrumentType.CE if option_type == "CE" else InstrumentType.PE,
            strike=strike,
            lot_size=strike_info.get('lotsize', 50),
            tick_size=0.05
        )
        
        # Create signal
        side = SignalSide.LONG if direction == "LONG" else SignalSide.SHORT
        entry_price = premium
        stop_loss = premium * (1 - SL_PCT)
        take_profit_1 = premium * (1 + TP1_PCT)
        take_profit_2 = premium * (1 + TP2_PCT)
        
        signal = self._create_signal(
            instrument=instrument,
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            confidence=momentum_score / 100.0,
            rationale=f"Delta: {delta:.3f}, IV Rank: {iv_rank:.1f}%, Momentum: {momentum_score:.1f}"
        )
        
        signals.append(signal)
        return signals
    
    def _market_time_ok(self, now: datetime) -> bool:
        """Check if market time is OK"""
        market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        if not (market_start <= now <= market_end):
            return False
        minutes_since_open = int((now - market_start).total_seconds() / 60)
        minutes_to_close = int((market_end - now).total_seconds() / 60)
        return minutes_since_open >= SKIP_FIRST_MINUTES and minutes_to_close >= SKIP_LAST_MINUTES
    
    def _get_history(self, context: StrategyContext) -> Optional[pd.DataFrame]:
        """Get historical data"""
        mock = get_mock()
        if not mock:
            return None
        
        # Get last 7 days of data
        end_date = context.timestamp.strftime("%Y-%m-%d")
        start_date = (context.timestamp - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        
        data = mock.post_json("history/", {
            "symbol": UNDERLYING,
            "exchange": UNDERLYING_EXCHANGE,
            "interval": "5m",
            "start_date": start_date,
            "end_date": end_date,
        })
        
        if data.get("status") != "success" or not data.get("data"):
            return None
        
        df = pd.DataFrame(data["data"])
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            df = df.sort_values('time')
        
        return df
    
    def _get_nearest_expiry(self, mock) -> Optional[str]:
        """Get nearest expiry"""
        data = mock.post_json("expiry", {
            "symbol": UNDERLYING,
            "exchange": OPTIONS_EXCHANGE,
        })
        expiries = data.get("data") or []
        if not expiries:
            return None
        return expiries[0].replace("-", "").upper()
    
    def _select_strike_by_delta(self, mock, expiry: str, option_type: str, delta_min: float, delta_max: float) -> Optional[dict]:
        """Select strike based on delta"""
        # Get option chain
        chain_data = mock.post_json("optionchain", {
            "underlying": UNDERLYING,
            "exchange": UNDERLYING_EXCHANGE,
            "expiry_date": expiry,
            "strike_count": 10,
        })
        
        if chain_data.get("status") != "success":
            return None
        
        chain = chain_data.get("chain", [])
        if not chain:
            return None
        
        # Find best strike matching delta
        best_strike = None
        best_delta_diff = float('inf')
        
        for strike_data in chain:
            opt_data = strike_data.get("ce" if option_type == "CE" else "pe", {})
            if not opt_data:
                continue
            
            opt_symbol = opt_data.get("symbol") or f"{UNDERLYING}{int(strike_data['strike'])}{option_type}"
            
            # Get Greeks
            greeks_data = mock.post_json("optiongreeks", {
                "symbol": opt_symbol,
                "exchange": OPTIONS_EXCHANGE,
            })
            
            if greeks_data.get("status") != "success":
                continue
            
            greeks = greeks_data.get("greeks", {})
            delta = abs(greeks.get('delta', 0))
            
            if delta_min <= delta <= delta_max:
                delta_diff = abs(delta - (delta_min + delta_max) / 2)
                if delta_diff < best_delta_diff:
                    best_delta_diff = delta_diff
                    best_strike = {
                        'symbol': opt_symbol,
                        'strike': strike_data['strike'],
                        'delta': delta,
                        'gamma': greeks.get('gamma', 0),
                        'theta': greeks.get('theta', 0),
                        'vega': greeks.get('vega', 0),
                        'iv': greeks_data.get('implied_volatility', 15) / 100.0,
                        'ltp': opt_data.get('ltp', 0),
                        'lotsize': 50 if UNDERLYING == "NIFTY" else 25,
                        'oi': opt_data.get('oi', 0),
                        'volume': opt_data.get('volume', 0),
                    }
        
        return best_strike
    
    def _calculate_iv_rank_simple(self, current_iv: float) -> float:
        """Calculate IV rank (simplified)"""
        # Simplified: assume IV range 10-30% maps to rank 0-100%
        iv_rank = ((current_iv - 0.10) / 0.20) * 100
        return max(0, min(100, iv_rank))
    
    def _ema(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate EMA"""
        return series.ewm(span=period, adjust=False).mean()
    
    def _atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ATR"""
        tr = OptimizedIndicators.calculate_tr(df)
        return OptimizedIndicators.calculate_atr(df, period, tr)
    
    def _adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ADX"""
        high = df["high"]
        low = df["low"]
        plus_dm = high.diff()
        minus_dm = low.diff() * -1
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        tr = self._atr(df, 1)
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr.rolling(window=period).mean())
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr.rolling(window=period).mean())
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        return dx.rolling(window=period).mean()
    
    def _rsi(self, df: pd.DataFrame, period: int = None) -> pd.Series:
        """Calculate RSI"""
        period = period or self.rsi_period
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        out = 100 - (100 / (1 + rs))
        return out.fillna(50)
    
    def _vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate VWAP"""
        if "volume" not in df.columns:
            return df["close"]
        typical = (df["high"] + df["low"] + df["close"]) / 3
        out = (typical * df["volume"]).cumsum() / df["volume"].cumsum()
        return out.replace([np.inf, -np.inf], np.nan).ffill()
