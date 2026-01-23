"""Base strategy interface"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from packages.core.models import Bar, Instrument, Signal, SignalSide, Tick


@dataclass
class StrategyContext:
    """Context passed to strategy for signal generation"""
    timestamp: datetime
    instrument: Instrument
    
    # Market data
    latest_tick: Optional[Tick] = None
    bars_1s: List[Bar] = None
    bars_5s: List[Bar] = None
    
    # Portfolio state
    net_liquid: float = 0.0
    available_margin: float = 0.0
    open_positions: int = 0
    
    # Market regime
    iv_percentile: Optional[float] = None
    oi_change_pct: Optional[float] = None
    underlying_price: Optional[float] = None  # Price of the underlying asset (for options strategies)
    
    def __post_init__(self):
        if self.bars_1s is None:
            self.bars_1s = []
        if self.bars_5s is None:
            self.bars_5s = []


class Strategy(ABC):
    """
    Base class for all trading strategies.
    
    Each strategy must implement:
    - generate_signals(): Produce trading signals based on market data
    - validate(): Check if strategy can run in current conditions
    """
    
    def __init__(self, name: str, params: Dict[str, Any]):
        self.name = name
        self.params = params
        
        # Strategy state
        self.enabled = True
        self.max_positions = params.get("max_positions", 2)
        self.current_positions = 0
        
        # Performance tracking
        self.signals_generated = 0
        self.signals_executed = 0
        self.win_count = 0
        self.loss_count = 0
        self.total_pnl = 0.0
    
    @abstractmethod
    def generate_signals(self, context: StrategyContext) -> List[Signal]:
        """
        Generate trading signals based on current market context.
        
        Args:
            context: Market data and state
        
        Returns:
            List of Signal objects
        """
        pass
    
    def validate(self, context: StrategyContext) -> bool:
        """
        Validate if strategy can run in current conditions.
        
        Args:
            context: Market data and state
        
        Returns:
            True if strategy can run, False otherwise
        """
        if not self.enabled:
            return False
        
        if self.current_positions >= self.max_positions:
            return False
        
        # Ensure we have enough data
        if not context.latest_tick:
            return False
        
        return True
    
    def on_position_opened(self) -> None:
        """Callback when a position is opened from this strategy"""
        self.current_positions += 1
        self.signals_executed += 1
    
    def on_position_closed(self, pnl: float) -> None:
        """Callback when a position is closed from this strategy"""
        self.current_positions = max(0, self.current_positions - 1)
        self.total_pnl += pnl
        
        if pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate"""
        total_trades = self.win_count + self.loss_count
        if total_trades > 0:
            return (self.win_count / total_trades) * 100
        return 0.0
    
    @property
    def sharpe_ratio(self) -> float:
        """Calculate Sharpe ratio (placeholder - needs proper implementation)"""
        # In production, track returns series and compute properly
        return 0.0
    
    def get_param(self, key: str, default: Any = None) -> Any:
        """Get strategy parameter with default"""
        return self.params.get(key, default)
    
    def __repr__(self) -> str:
        return (
            f"{self.name}(enabled={self.enabled}, "
            f"positions={self.current_positions}/{self.max_positions}, "
            f"win_rate={self.win_rate:.1f}%)"
        )
