from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Rule:
    block_type: str # 'breakout', 'trend', 'mean_reversion', 'volatility'
    indicator: str
    params: Dict[str, Any]
    operator: str # '>', '<', 'cross_above', 'cross_below'
    threshold: Any # Value or another indicator

@dataclass
class Filter:
    filter_type: str # 'regime', 'volatility', 'time'
    indicator: str
    params: Dict[str, Any]
    operator: str
    threshold: Any

@dataclass
class StrategyConfig:
    strategy_id: str
    entry_rules: List[Rule]
    filters: List[Filter]

    # Risk Params
    stop_loss_atr: float
    take_profit_atr: float
    trailing_stop_atr: Optional[float]
    max_bars_hold: int

    # Intraday Params
    exit_time: str = "15:25"

    def to_dict(self):
        return {
            "strategy_id": self.strategy_id,
            "entry_rules": [vars(r) for r in self.entry_rules],
            "filters": [vars(f) for f in self.filters],
            "stop_loss_atr": self.stop_loss_atr,
            "take_profit_atr": self.take_profit_atr,
            "trailing_stop_atr": self.trailing_stop_atr,
            "max_bars_hold": self.max_bars_hold,
            "exit_time": self.exit_time
        }
