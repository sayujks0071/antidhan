"""Opening Range Breakout (ORB) Strategy"""
from datetime import datetime, time, timedelta
from typing import List

import structlog

from packages.core.models import Bar, Signal, SignalSide
from packages.core.strategies.base import Strategy, StrategyContext

logger = structlog.get_logger(__name__)


class ORBStrategy(Strategy):
    """
    Opening Range Breakout Strategy
    
    Logic:
    1. Define opening range as first N minutes of trading (e.g., 15 minutes)
    2. Track high and low of this period
    3. Enter LONG on breakout above high with confirmation
    4. Enter SHORT on breakdown below low with confirmation
    5. Set stop at opposite end of range
    6. Target based on range size * RR multiplier
    
    Parameters:
    - window_min: Opening range window in minutes (default: 15)
    - breakout_confirmation_ticks: Number of ticks to confirm breakout (default: 3)
    - rr_min: Minimum risk-reward ratio (default: 1.8)
    - max_positions: Maximum concurrent positions (default: 2)
    - instruments: List of instruments to trade (default: ["NIFTY", "BANKNIFTY"])
    """
    
    def __init__(self, name: str, params: dict):
        super().__init__(name, params)
        
        self.window_min = params.get("window_min", 15)
        self.breakout_confirmation_ticks = params.get("breakout_confirmation_ticks", 3)
        self.rr_min = params.get("rr_min", 1.8)
        self.allowed_instruments = params.get("instruments", ["NIFTY", "BANKNIFTY"])
        
        # State tracking
        self.opening_ranges: dict = {}  # instrument_token -> (high, low, end_time)
        self.breakout_confirmed: dict = {}  # instrument_token -> (direction, count)
    
    def generate_signals(self, context: StrategyContext) -> List[Signal]:
        """Generate ORB signals"""
        if not self.validate(context):
            return []
        
        # Check if instrument is allowed
        if context.instrument.symbol not in self.allowed_instruments:
            return []
        
        # Check if we have enough bar data
        if not context.bars_5s or len(context.bars_5s) < 5:
            return []
        
        signals = []
        token = context.instrument.token
        current_time = context.timestamp.time()
        market_open = time(9, 15)  # IST market open
        
        # Calculate opening range end time
        or_end = (
            datetime.combine(context.timestamp.date(), market_open) +
            timedelta(minutes=self.window_min)
        ).time()
        
        # Build or update opening range
        if current_time < or_end:
            self._update_opening_range(token, context.bars_5s, context.timestamp)
            return []
        
        # Check if opening range exists
        if token not in self.opening_ranges:
            return []
        
        or_high, or_low, _ = self.opening_ranges[token]
        latest_bar = context.bars_5s[-1]
        current_price = context.latest_tick.last_price
        
        # Check for breakout
        if current_price > or_high:
            # Potential LONG breakout
            if not self._is_breakout_confirmed(token, "LONG"):
                self._increment_breakout_confirmation(token, "LONG")
                return []
            
            # Generate LONG signal
            signal = self._create_long_signal(
                context,
                entry_price=current_price,
                stop_loss=or_low,
                or_range=or_high - or_low
            )
            
            if signal:
                signals.append(signal)
                self._reset_breakout_confirmation(token)
                logger.info(
                    "ORB LONG signal generated",
                    instrument=context.instrument.tradingsymbol,
                    entry=signal.entry_price,
                    stop=signal.stop_loss
                )
        
        elif current_price < or_low:
            # Potential SHORT breakout
            if not self._is_breakout_confirmed(token, "SHORT"):
                self._increment_breakout_confirmation(token, "SHORT")
                return []
            
            # Generate SHORT signal
            signal = self._create_short_signal(
                context,
                entry_price=current_price,
                stop_loss=or_high,
                or_range=or_high - or_low
            )
            
            if signal:
                signals.append(signal)
                self._reset_breakout_confirmation(token)
                logger.info(
                    "ORB SHORT signal generated",
                    instrument=context.instrument.tradingsymbol,
                    entry=signal.entry_price,
                    stop=signal.stop_loss
                )
        
        else:
            # Price back in range, reset confirmation
            self._reset_breakout_confirmation(token)
        
        return signals
    
    def _update_opening_range(self, token: int, bars: List[Bar], timestamp: datetime) -> None:
        """Update opening range for an instrument"""
        if not bars:
            return
        
        # Calculate high and low from bars
        highs = [bar.high for bar in bars]
        lows = [bar.low for bar in bars]
        
        or_high = max(highs)
        or_low = min(lows)
        
        market_open = time(9, 15)
        or_end = (
            datetime.combine(timestamp.date(), market_open) +
            timedelta(minutes=self.window_min)
        )
        
        self.opening_ranges[token] = (or_high, or_low, or_end)
    
    def _is_breakout_confirmed(self, token: int, direction: str) -> bool:
        """Check if breakout is confirmed"""
        if token not in self.breakout_confirmed:
            return False
        
        conf_direction, count = self.breakout_confirmed[token]
        
        return conf_direction == direction and count >= self.breakout_confirmation_ticks
    
    def _increment_breakout_confirmation(self, token: int, direction: str) -> None:
        """Increment breakout confirmation counter"""
        if token in self.breakout_confirmed:
            conf_direction, count = self.breakout_confirmed[token]
            if conf_direction == direction:
                self.breakout_confirmed[token] = (direction, count + 1)
            else:
                # Direction changed, reset
                self.breakout_confirmed[token] = (direction, 1)
        else:
            self.breakout_confirmed[token] = (direction, 1)
    
    def _reset_breakout_confirmation(self, token: int) -> None:
        """Reset breakout confirmation"""
        if token in self.breakout_confirmed:
            del self.breakout_confirmed[token]
    
    def _create_long_signal(
        self,
        context: StrategyContext,
        entry_price: float,
        stop_loss: float,
        or_range: float
    ) -> Signal:
        """Create LONG signal with proper risk-reward"""
        risk = entry_price - stop_loss
        
        if risk <= 0:
            return None
        
        # Calculate target based on RR ratio
        reward = risk * self.rr_min
        take_profit_1 = entry_price + (reward * 0.6)  # TP1 at 60% of target
        take_profit_2 = entry_price + reward  # TP2 at full target
        
        signal = Signal(
            strategy_name=self.name,
            timestamp=context.timestamp,
            instrument=context.instrument,
            side=SignalSide.LONG,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            confidence=0.75,
            rationale=f"ORB breakout above {entry_price:.2f}, range: {or_range:.2f}",
            features={
                "or_high": entry_price,
                "or_low": stop_loss,
                "or_range": or_range,
                "breakout_type": "LONG"
            }
        )
        
        signal.risk_amount = risk
        signal.reward_amount = reward
        
        self.signals_generated += 1
        
        return signal
    
    def _create_short_signal(
        self,
        context: StrategyContext,
        entry_price: float,
        stop_loss: float,
        or_range: float
    ) -> Signal:
        """Create SHORT signal with proper risk-reward"""
        risk = stop_loss - entry_price
        
        if risk <= 0:
            return None
        
        # Calculate target based on RR ratio
        reward = risk * self.rr_min
        take_profit_1 = entry_price - (reward * 0.6)  # TP1 at 60% of target
        take_profit_2 = entry_price - reward  # TP2 at full target
        
        signal = Signal(
            strategy_name=self.name,
            timestamp=context.timestamp,
            instrument=context.instrument,
            side=SignalSide.SHORT,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            confidence=0.75,
            rationale=f"ORB breakdown below {entry_price:.2f}, range: {or_range:.2f}",
            features={
                "or_high": stop_loss,
                "or_low": entry_price,
                "or_range": or_range,
                "breakout_type": "SHORT"
            }
        )
        
        signal.risk_amount = risk
        signal.reward_amount = reward
        
        self.signals_generated += 1
        
        return signal
    
    def validate(self, context: StrategyContext) -> bool:
        """Validate ORB strategy can run"""
        if not super().validate(context):
            return False
        
        # Only trade during regular market hours (after opening range)
        current_time = context.timestamp.time()
        market_open = time(9, 15)
        market_close = time(15, 25)  # Stop before EOD
        
        # Allow execution during the opening range window to collect data
        # Execution is also allowed after the window for signal generation
        if not (market_open <= current_time < market_close):
            return False
        
        return True
