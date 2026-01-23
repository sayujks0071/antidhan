"""
AITRAPP-Inspired Utilities for OpenAlgo Strategies
════════════════════════════════════════════════════════════════════════════

Shared utilities based on AITRAPP production-grade patterns:
- Advanced exit management (volatility stops, MAE stops)
- Better position sizing
- Portfolio heat tracking
- Optimized indicators
"""
import math
from typing import Dict, Optional, Tuple
import pandas as pd
import numpy as np


class ExitManager:
    """
    Advanced exit management with multiple stop types.
    Based on AITRAPP packages/core/exits.py
    """
    
    @staticmethod
    def check_volatility_stop(
        current_atr: float,
        baseline_atr: float,
        spike_multiplier: float = 2.0
    ) -> Tuple[bool, str]:
        """
        Check if volatility spike requires exit.
        
        Args:
            current_atr: Current ATR value
            baseline_atr: Baseline ATR (e.g., 20-period average)
            spike_multiplier: Exit if ATR > baseline * multiplier
        
        Returns:
            (should_exit, reason)
        """
        if baseline_atr <= 0:
            return False, ""
        
        if current_atr > baseline_atr * spike_multiplier:
            return True, f"Volatility spike: ATR {current_atr:.2f} > {baseline_atr * spike_multiplier:.2f}"
        
        return False, ""
    
    @staticmethod
    def check_mae_stop(
        current_pnl: float,
        max_adverse: float,
        account_size: float,
        mae_limit_pct: float = 1.5
    ) -> Tuple[bool, str, float]:
        """
        Check Maximum Adverse Excursion (MAE) stop.
        
        Args:
            current_pnl: Current unrealized P&L
            max_adverse: Maximum adverse excursion so far
            account_size: Account size
            mae_limit_pct: MAE limit as % of account
        
        Returns:
            (should_exit, reason, updated_max_adverse)
        """
        mae_limit = account_size * (mae_limit_pct / 100)
        
        # Update max adverse if current loss is worse
        if current_pnl < max_adverse:
            max_adverse = current_pnl
        
        # Check if MAE limit breached
        if abs(max_adverse) > mae_limit:
            return True, f"MAE stop: {max_adverse:.2f} exceeds limit {mae_limit:.2f}", max_adverse
        
        return False, "", max_adverse
    
    @staticmethod
    def check_time_stop(
        entry_time,
        current_time,
        max_hold_minutes: int
    ) -> Tuple[bool, str]:
        """
        Check if position should exit due to time limit.
        
        Args:
            entry_time: Position entry timestamp
            current_time: Current timestamp
            max_hold_minutes: Maximum hold time in minutes
        
        Returns:
            (should_exit, reason)
        """
        hold_minutes = (current_time - entry_time).total_seconds() / 60
        
        if hold_minutes >= max_hold_minutes:
            return True, f"Time stop: held {hold_minutes:.1f} min (max {max_hold_minutes})"
        
        return False, ""
    
    @staticmethod
    def move_stop_to_breakeven(
        entry_price: float,
        current_price: float,
        direction: str,
        current_stop: float
    ) -> float:
        """
        Move stop to breakeven after profit target hit.
        
        Args:
            entry_price: Entry price
            current_price: Current price
            direction: "LONG" or "SHORT"
            current_stop: Current stop loss price
        
        Returns:
            New stop price (breakeven or current stop, whichever is better)
        """
        if direction == "LONG":
            # For long, breakeven is entry price
            # New stop should be max(entry, current_stop) to protect profit
            return max(entry_price, current_stop)
        else:  # SHORT
            # For short, breakeven is entry price
            # New stop should be min(entry, current_stop) to protect profit
            return min(entry_price, current_stop)


class PositionSizer:
    """
    Better position sizing based on AITRAPP patterns.
    Based on AITRAPP packages/core/risk.py
    """
    
    @staticmethod
    def calculate_position_size(
        option_ltp: float,
        lotsize: int,
        stop_distance: float,
        net_liquid: float,
        risk_pct: float = 0.5,
        max_position_multiplier: int = 3
    ) -> int:
        """
        Calculate position size with proper lot handling.
        
        Formula: Position Size = (Capital * Risk%) / Stop Distance
        
        Args:
            option_ltp: Option LTP
            lotsize: Lot size
            stop_distance: Stop loss distance (in price units)
            net_liquid: Net liquid capital
            risk_pct: Risk per trade percentage
            max_position_multiplier: Maximum lots multiplier
        
        Returns:
            Position size in quantity (not lots)
        """
        if stop_distance <= 0:
            return 0
        
        # Calculate risk amount
        risk_amount = net_liquid * (risk_pct / 100)
        
        # Calculate quantity
        quantity = risk_amount / stop_distance
        
        # Apply max position size multiplier
        max_quantity = lotsize * max_position_multiplier
        quantity = min(quantity, max_quantity)
        
        # Round to lot size for F&O
        if lotsize > 1:
            lots = int(quantity / lotsize)
            lots = max(1, lots)  # At least 1 lot
            return lots * lotsize
        
        # For non-F&O, round to integer
        return max(1, int(quantity))
    
    @staticmethod
    def calculate_stop_distance(
        entry_price: float,
        stop_loss_pct: float,
        direction: str
    ) -> float:
        """
        Calculate stop distance in price units.
        
        Args:
            entry_price: Entry price
            stop_loss_pct: Stop loss percentage
            direction: "LONG" or "SHORT"
        
        Returns:
            Stop distance in price units
        """
        if direction == "LONG":
            return entry_price * stop_loss_pct
        else:  # SHORT
            return entry_price * stop_loss_pct


class PortfolioHeatTracker:
    """
    Portfolio heat tracking - aggregate risk across all positions.
    Based on AITRAPP packages/core/risk.py
    """
    
    def __init__(self, account_size: float, max_heat_pct: float = 2.0):
        self.account_size = account_size
        self.max_heat_pct = max_heat_pct
        self.positions: Dict[str, Dict] = {}
    
    def add_position(
        self,
        position_id: str,
        risk_amount: float,
        entry_time
    ):
        """Add position to heat tracking"""
        self.positions[position_id] = {
            'risk_amount': risk_amount,
            'entry_time': entry_time
        }
    
    def remove_position(self, position_id: str):
        """Remove position from heat tracking"""
        if position_id in self.positions:
            del self.positions[position_id]
    
    def get_total_risk(self) -> float:
        """Get total risk across all positions"""
        return sum(pos['risk_amount'] for pos in self.positions.values())
    
    def get_portfolio_heat_pct(self) -> float:
        """Get portfolio heat as percentage of account"""
        total_risk = self.get_total_risk()
        if self.account_size > 0:
            return (total_risk / self.account_size) * 100
        return 0.0
    
    def can_take_new_position(self, new_risk_amount: float) -> Tuple[bool, str]:
        """
        Check if new position can be taken based on portfolio heat.
        
        Args:
            new_risk_amount: Risk amount for new position
        
        Returns:
            (can_take, reason)
        """
        current_heat = self.get_portfolio_heat_pct()
        new_heat = ((self.get_total_risk() + new_risk_amount) / self.account_size) * 100
        
        if new_heat > self.max_heat_pct:
            return False, f"Portfolio heat limit: {new_heat:.2f}% > {self.max_heat_pct}%"
        
        return True, f"Heat OK: {new_heat:.2f}%"


class OptimizedIndicators:
    """
    Optimized indicator calculations.
    Based on AITRAPP packages/core/indicators.py
    """
    
    @staticmethod
    def calculate_tr(df: pd.DataFrame) -> pd.Series:
        """Calculate True Range (reused for ATR, ADX, Supertrend)"""
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14, tr: pd.Series = None) -> pd.Series:
        """Calculate ATR (reuse TR if provided)"""
        if tr is None:
            tr = OptimizedIndicators.calculate_tr(df)
        return tr.rolling(window=period).mean()
    
    @staticmethod
    def calculate_baseline_atr(df: pd.DataFrame, period: int = 14, lookback: int = 20) -> float:
        """
        Calculate baseline ATR for volatility stop.
        Returns average of last N ATR values.
        """
        atr_series = OptimizedIndicators.calculate_atr(df, period)
        if len(atr_series) >= lookback:
            return atr_series.iloc[-lookback:].mean()
        elif len(atr_series) > 0:
            return atr_series.mean()
        return 0.0


def calculate_iv_percentile_simplified(current_vix: float, vix_min: float = 10.0, vix_max: float = 30.0) -> float:
    """
    Simplified IV percentile calculation using VIX as proxy.
    Based on AITRAPP options_ranker pattern.
    
    Args:
        current_vix: Current VIX value
        vix_min: Minimum VIX in range
        vix_max: Maximum VIX in range
    
    Returns:
        IV percentile (0-100)
    """
    if vix_max <= vix_min:
        return 50.0
    
    iv_rank = ((current_vix - vix_min) / (vix_max - vix_min)) * 100
    return max(0.0, min(100.0, iv_rank))


def calculate_liquidity_score(
    oi: int,
    volume: int,
    bid: float,
    ask: float,
    ltp: float
) -> float:
    """
    Calculate liquidity score (0-1) for options.
    Based on AITRAPP options_ranker pattern.
    
    Args:
        oi: Open interest
        volume: Volume
        bid: Bid price
        ask: Ask price
        ltp: Last traded price
    
    Returns:
        Liquidity score (0-1, higher is better)
    """
    if ltp <= 0:
        return 0.0
    
    # OI score (normalized)
    oi_score = min(1.0, oi / 1000000)  # 1M OI = max score
    
    # Volume score (normalized)
    volume_score = min(1.0, volume / 100000)  # 100K volume = max score
    
    # Spread score (lower spread = better)
    spread_pct = (ask - bid) / ltp if ltp > 0 else 1.0
    spread_score = max(0.0, 1.0 - (spread_pct * 10))  # 10% spread = 0 score
    
    # Weighted average
    liquidity_score = (oi_score * 0.4) + (volume_score * 0.4) + (spread_score * 0.2)
    
    return liquidity_score
