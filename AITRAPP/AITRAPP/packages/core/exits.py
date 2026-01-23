"""Exit management with multiple stop types"""
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

import structlog

from packages.core.config import ExitsConfig
from packages.core.models import Bar, Position, SignalSide, Tick

logger = structlog.get_logger(__name__)


class ExitReason(str, Enum):
    """Exit trigger reasons"""
    STOP_LOSS = "STOP_LOSS"
    TRAILING_STOP = "TRAILING_STOP"
    TAKE_PROFIT_1 = "TAKE_PROFIT_1"
    TAKE_PROFIT_2 = "TAKE_PROFIT_2"
    TIME_STOP = "TIME_STOP"
    VOLATILITY_STOP = "VOLATILITY_STOP"
    MAE_STOP = "MAE_STOP"
    EOD_SQUAREOFF = "EOD_SQUAREOFF"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    MANUAL = "MANUAL"


class ExitSignal:
    """Exit signal with reason and urgency"""
    def __init__(
        self,
        position_id: str,
        reason: ExitReason,
        urgency: str = "NORMAL",  # NORMAL | URGENT
        details: Optional[Dict] = None
    ):
        self.position_id = position_id
        self.reason = reason
        self.urgency = urgency
        self.details = details or {}
        self.timestamp = datetime.now()


class ExitManager:
    """
    Manages position exits with multiple stop types:
    - Hard stop loss
    - Trailing stop (ATR-based or step-based)
    - Take profit levels with partials
    - Time-based stop
    - Volatility spike stop
    - Maximum adverse excursion (MAE) stop
    - EOD auto square-off
    """
    
    def __init__(self, config: ExitsConfig):
        self.config = config
        
        # Position tracking
        self.position_entry_times: Dict[str, datetime] = {}
        self.position_baseline_atr: Dict[str, float] = {}
        self.tp1_hit: Dict[str, bool] = {}
    
    def check_exits(
        self,
        positions: List[Position],
        market_data: Dict[int, tuple[Tick, List[Bar]]],
        current_time: datetime,
        daily_pnl_pct: float,
        net_liquid: float
    ) -> List[ExitSignal]:
        """
        Check all positions for exit conditions.
        
        Args:
            positions: List of open positions
            market_data: Dict of token -> (tick, bars)
            current_time: Current timestamp
            daily_pnl_pct: Daily P&L percentage
            net_liquid: Net liquid capital
        
        Returns:
            List of exit signals
        """
        exit_signals = []
        
        for position in positions:
            if not position.is_open:
                continue
            
            # Get market data
            tick_bars = market_data.get(position.instrument.token)
            if not tick_bars:
                continue
            
            tick, bars = tick_bars
            
            # Update position with current price
            position.current_price = tick.last_price
            position.update_pnl()
            
            # Initialize tracking
            if position.position_id not in self.position_entry_times:
                self.position_entry_times[position.position_id] = position.entry_time
                
                # Store baseline ATR
                if bars and bars[-1].atr:
                    self.position_baseline_atr[position.position_id] = bars[-1].atr
            
            # Check each exit condition
            
            # 1. Hard stop loss
            if self._check_hard_stop(position):
                exit_signals.append(ExitSignal(
                    position.position_id,
                    ExitReason.STOP_LOSS,
                    urgency="URGENT",
                    details={"stop_price": position.stop_loss}
                ))
                continue
            
            # 2. Trailing stop
            if self.config.trail_enabled:
                trailing_exit = self._check_trailing_stop(position, bars)
                if trailing_exit:
                    exit_signals.append(trailing_exit)
                    continue
            
            # 3. Take profit levels
            tp_exit = self._check_take_profit(position)
            if tp_exit:
                exit_signals.append(tp_exit)
                continue
            
            # 4. Time stop
            if self.config.time_stop_enabled:
                time_exit = self._check_time_stop(position, current_time)
                if time_exit:
                    exit_signals.append(time_exit)
                    continue
            
            # 5. Volatility stop
            if self.config.vol_stop_enabled:
                vol_exit = self._check_volatility_stop(position, bars)
                if vol_exit:
                    exit_signals.append(vol_exit)
                    continue
            
            # 6. MAE stop
            if self.config.mae_stop_enabled:
                mae_exit = self._check_mae_stop(position, net_liquid)
                if mae_exit:
                    exit_signals.append(mae_exit)
                    continue
            
            # 7. EOD square-off
            eod_exit = self._check_eod_squareoff(position, current_time)
            if eod_exit:
                exit_signals.append(eod_exit)
                continue
        
        if exit_signals:
            logger.info(f"Generated {len(exit_signals)} exit signals")
        
        return exit_signals
    
    def _check_hard_stop(self, position: Position) -> bool:
        """Check if hard stop loss is hit"""
        if position.side == SignalSide.LONG:
            return position.current_price <= position.stop_loss
        else:
            return position.current_price >= position.stop_loss
    
    def _check_trailing_stop(
        self,
        position: Position,
        bars: List[Bar]
    ) -> Optional[ExitSignal]:
        """
        Check and update trailing stop.
        
        ATR-based trailing stop that only moves in favorable direction.
        """
        if not bars or not bars[-1].atr:
            return None
        
        atr = bars[-1].atr
        trail_distance = atr * self.config.trail_atr_mult
        
        # Update trailing stop
        if position.side == SignalSide.LONG:
            # For LONG: trail below price
            new_trail = position.current_price - trail_distance
            
            # Only move stop up (never down)
            if position.trailing_stop is None:
                position.trailing_stop = max(position.stop_loss, new_trail)
            else:
                position.trailing_stop = max(position.trailing_stop, new_trail)
            
            # Check if trailing stop is hit
            if position.current_price <= position.trailing_stop:
                return ExitSignal(
                    position.position_id,
                    ExitReason.TRAILING_STOP,
                    urgency="URGENT",
                    details={
                        "trailing_stop": position.trailing_stop,
                        "current_price": position.current_price
                    }
                )
        
        else:  # SHORT
            # For SHORT: trail above price
            new_trail = position.current_price + trail_distance
            
            # Only move stop down (never up)
            if position.trailing_stop is None:
                position.trailing_stop = min(position.stop_loss, new_trail)
            else:
                position.trailing_stop = min(position.trailing_stop, new_trail)
            
            # Check if trailing stop is hit
            if position.current_price >= position.trailing_stop:
                return ExitSignal(
                    position.position_id,
                    ExitReason.TRAILING_STOP,
                    urgency="URGENT",
                    details={
                        "trailing_stop": position.trailing_stop,
                        "current_price": position.current_price
                    }
                )
        
        return None
    
    def _check_take_profit(self, position: Position) -> Optional[ExitSignal]:
        """Check if take profit levels are hit"""
        # TP1 check
        if position.take_profit_1 and position.position_id not in self.tp1_hit:
            tp1_hit = False
            
            if position.side == SignalSide.LONG:
                tp1_hit = position.current_price >= position.take_profit_1
            else:
                tp1_hit = position.current_price <= position.take_profit_1
            
            if tp1_hit:
                self.tp1_hit[position.position_id] = True
                
                # Move stop to breakeven
                if self.config.move_to_be_after_tp1:
                    position.stop_loss = position.entry_price
                    logger.info(
                        "Stop moved to breakeven after TP1",
                        position_id=position.position_id
                    )
                
                return ExitSignal(
                    position.position_id,
                    ExitReason.TAKE_PROFIT_1,
                    urgency="NORMAL",
                    details={
                        "target": position.take_profit_1,
                        "partial_pct": self.config.tp1_partial_pct
                    }
                )
        
        # TP2 check
        if position.take_profit_2:
            tp2_hit = False
            
            if position.side == SignalSide.LONG:
                tp2_hit = position.current_price >= position.take_profit_2
            else:
                tp2_hit = position.current_price <= position.take_profit_2
            
            if tp2_hit:
                return ExitSignal(
                    position.position_id,
                    ExitReason.TAKE_PROFIT_2,
                    urgency="NORMAL",
                    details={
                        "target": position.take_profit_2,
                        "partial_pct": self.config.tp2_partial_pct
                    }
                )
        
        return None
    
    def _check_time_stop(
        self,
        position: Position,
        current_time: datetime
    ) -> Optional[ExitSignal]:
        """Check if time stop is triggered"""
        entry_time = self.position_entry_times.get(position.position_id)
        
        if not entry_time:
            return None
        
        duration = (current_time - entry_time).total_seconds() / 60
        
        # If position hasn't moved favorably after time limit, exit
        if duration >= self.config.time_stop_min:
            # Check if position is in profit
            if position.unrealized_pnl <= 0:
                return ExitSignal(
                    position.position_id,
                    ExitReason.TIME_STOP,
                    urgency="NORMAL",
                    details={
                        "duration_minutes": duration,
                        "pnl": position.unrealized_pnl
                    }
                )
        
        return None
    
    def _check_volatility_stop(
        self,
        position: Position,
        bars: List[Bar]
    ) -> Optional[ExitSignal]:
        """Check if volatility has spiked beyond acceptable levels"""
        if not bars or not bars[-1].atr:
            return None
        
        current_atr = bars[-1].atr
        baseline_atr = self.position_baseline_atr.get(position.position_id)
        
        if not baseline_atr:
            return None
        
        # Check for volatility spike
        atr_ratio = current_atr / baseline_atr
        
        if atr_ratio >= self.config.vol_spike_mult:
            return ExitSignal(
                position.position_id,
                ExitReason.VOLATILITY_STOP,
                urgency="URGENT",
                details={
                    "current_atr": current_atr,
                    "baseline_atr": baseline_atr,
                    "ratio": atr_ratio
                }
            )
        
        return None
    
    def _check_mae_stop(
        self,
        position: Position,
        net_liquid: float
    ) -> Optional[ExitSignal]:
        """Check if maximum adverse excursion exceeds threshold"""
        mae_pct = (position.max_adverse_excursion / net_liquid) * 100
        
        if abs(mae_pct) >= self.config.mae_stop_pct:
            return ExitSignal(
                position.position_id,
                ExitReason.MAE_STOP,
                urgency="URGENT",
                details={
                    "mae": position.max_adverse_excursion,
                    "mae_pct": mae_pct,
                    "threshold": self.config.mae_stop_pct
                }
            )
        
        return None
    
    def _check_eod_squareoff(
        self,
        position: Position,
        current_time: datetime
    ) -> Optional[ExitSignal]:
        """Check if EOD square-off time is reached"""
        eod_time = datetime.strptime("15:25", "%H:%M").time()
        
        if current_time.time() >= eod_time:
            return ExitSignal(
                position.position_id,
                ExitReason.EOD_SQUAREOFF,
                urgency="URGENT",
                details={"time": current_time.isoformat()}
            )
        
        return None
    
    def on_position_closed(self, position_id: str) -> None:
        """Clean up tracking when position is closed"""
        self.position_entry_times.pop(position_id, None)
        self.position_baseline_atr.pop(position_id, None)
        self.tp1_hit.pop(position_id, None)
        
        logger.debug("Exit tracking cleared", position_id=position_id)
