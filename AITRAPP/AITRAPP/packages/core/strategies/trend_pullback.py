"""Trend Pullback Strategy"""
from typing import List, Optional

import structlog

from packages.core.models import Bar, Signal, SignalSide
from packages.core.strategies.base import Strategy, StrategyContext

logger = structlog.get_logger(__name__)


class TrendPullbackStrategy(Strategy):
    """
    Trend Pullback Strategy
    
    Logic:
    1. Identify trend using EMA crossover (fast EMA > slow EMA = uptrend)
    2. Wait for pullback to EMA or ATR band
    3. Enter when price bounces back in trend direction
    4. Stop below/above recent swing
    5. Target based on ATR multiple
    
    Parameters:
    - ema_fast: Fast EMA period (default: 34)
    - ema_slow: Slow EMA period (default: 89)
    - atr_period: ATR period (default: 14)
    - pullback_atr_mult: ATR multiplier for pullback zone (default: 0.5)
    - rr_min: Minimum risk-reward ratio (default: 2.0)
    - max_positions: Maximum concurrent positions (default: 2)
    """
    
    def __init__(self, name: str, params: dict):
        super().__init__(name, params)
        
        self.ema_fast = params.get("ema_fast", 34)
        self.ema_slow = params.get("ema_slow", 89)
        self.atr_period = params.get("atr_period", 14)
        self.pullback_atr_mult = params.get("pullback_atr_mult", 0.5)
        self.rr_min = params.get("rr_min", 2.0)
        
        # State tracking
        self.last_signal_time: dict = {}  # instrument_token -> timestamp
        self.min_signal_gap_minutes = 15
    
    def generate_signals(self, context: StrategyContext) -> List[Signal]:
        """Generate trend pullback signals"""
        if not self.validate(context):
            return []
        
        # Need sufficient bar data
        if not context.bars_5s or len(context.bars_5s) < max(self.ema_slow, self.atr_period) + 10:
            return []
        
        latest_bar = context.bars_5s[-1]
        
        # Get indicators from latest bar
        if not all([latest_bar.ema_fast, latest_bar.ema_slow, latest_bar.atr]):
            logger.debug("Missing indicators", instrument=context.instrument.tradingsymbol)
            return []
        
        ema_fast = latest_bar.ema_fast
        ema_slow = latest_bar.ema_slow
        atr = latest_bar.atr
        current_price = context.latest_tick.last_price
        
        signals = []
        
        # Identify trend
        trend = self._identify_trend(ema_fast, ema_slow)
        
        if trend == "UPTREND":
            signal = self._check_long_pullback(
                context,
                current_price,
                ema_fast,
                ema_slow,
                atr,
                context.bars_5s
            )
            if signal:
                signals.append(signal)
        
        elif trend == "DOWNTREND":
            signal = self._check_short_pullback(
                context,
                current_price,
                ema_fast,
                ema_slow,
                atr,
                context.bars_5s
            )
            if signal:
                signals.append(signal)
        
        return signals
    
    def _identify_trend(self, ema_fast: float, ema_slow: float) -> str:
        """Identify current trend"""
        if ema_fast > ema_slow * 1.002:  # 0.2% buffer
            return "UPTREND"
        elif ema_fast < ema_slow * 0.998:
            return "DOWNTREND"
        return "SIDEWAYS"
    
    def _check_long_pullback(
        self,
        context: StrategyContext,
        current_price: float,
        ema_fast: float,
        ema_slow: float,
        atr: float,
        bars: List[Bar]
    ) -> Optional[Signal]:
        """Check for long pullback setup"""
        # Price should have pulled back to fast EMA or ATR band
        pullback_zone_low = ema_fast - (atr * self.pullback_atr_mult)
        pullback_zone_high = ema_fast + (atr * self.pullback_atr_mult)
        
        # Check if price is in pullback zone
        if not (pullback_zone_low <= current_price <= pullback_zone_high):
            return None
        
        # Check for bounce (recent bars showing rejection)
        if not self._has_bullish_bounce(bars[-5:]):
            return None
        
        # Avoid too frequent signals
        if not self._can_generate_signal(context.instrument.token, context.timestamp):
            return None
        
        # Calculate entry, stop, and targets
        entry_price = current_price
        
        # Stop below recent swing low or slow EMA
        recent_low = min([bar.low for bar in bars[-10:]])
        stop_loss = min(recent_low, ema_slow - atr)
        
        risk = entry_price - stop_loss
        
        if risk <= 0 or risk > atr * 3:  # Risk too large
            return None
        
        # Calculate targets
        reward = risk * self.rr_min
        take_profit_1 = entry_price + (reward * 0.6)
        take_profit_2 = entry_price + reward
        
        signal = Signal(
            strategy_name=self.name,
            timestamp=context.timestamp,
            instrument=context.instrument,
            side=SignalSide.LONG,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            confidence=0.70,
            rationale=f"Uptrend pullback to EMA, bounce at {entry_price:.2f}",
            features={
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "atr": atr,
                "trend": "UPTREND",
                "pullback_zone_low": pullback_zone_low,
                "pullback_zone_high": pullback_zone_high
            }
        )
        
        signal.risk_amount = risk
        signal.reward_amount = reward
        
        self.signals_generated += 1
        self.last_signal_time[context.instrument.token] = context.timestamp
        
        logger.info(
            "Trend pullback LONG signal",
            instrument=context.instrument.tradingsymbol,
            entry=entry_price,
            stop=stop_loss,
            rr=signal.risk_reward_ratio
        )
        
        return signal
    
    def _check_short_pullback(
        self,
        context: StrategyContext,
        current_price: float,
        ema_fast: float,
        ema_slow: float,
        atr: float,
        bars: List[Bar]
    ) -> Optional[Signal]:
        """Check for short pullback setup"""
        # Price should have pulled back to fast EMA or ATR band
        pullback_zone_low = ema_fast - (atr * self.pullback_atr_mult)
        pullback_zone_high = ema_fast + (atr * self.pullback_atr_mult)
        
        # Check if price is in pullback zone
        if not (pullback_zone_low <= current_price <= pullback_zone_high):
            return None
        
        # Check for bounce (recent bars showing rejection)
        if not self._has_bearish_bounce(bars[-5:]):
            return None
        
        # Avoid too frequent signals
        if not self._can_generate_signal(context.instrument.token, context.timestamp):
            return None
        
        # Calculate entry, stop, and targets
        entry_price = current_price
        
        # Stop above recent swing high or slow EMA
        recent_high = max([bar.high for bar in bars[-10:]])
        stop_loss = max(recent_high, ema_slow + atr)
        
        risk = stop_loss - entry_price
        
        if risk <= 0 or risk > atr * 3:  # Risk too large
            return None
        
        # Calculate targets
        reward = risk * self.rr_min
        take_profit_1 = entry_price - (reward * 0.6)
        take_profit_2 = entry_price - reward
        
        signal = Signal(
            strategy_name=self.name,
            timestamp=context.timestamp,
            instrument=context.instrument,
            side=SignalSide.SHORT,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            confidence=0.70,
            rationale=f"Downtrend pullback to EMA, rejection at {entry_price:.2f}",
            features={
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "atr": atr,
                "trend": "DOWNTREND",
                "pullback_zone_low": pullback_zone_low,
                "pullback_zone_high": pullback_zone_high
            }
        )
        
        signal.risk_amount = risk
        signal.reward_amount = reward
        
        self.signals_generated += 1
        self.last_signal_time[context.instrument.token] = context.timestamp
        
        logger.info(
            "Trend pullback SHORT signal",
            instrument=context.instrument.tradingsymbol,
            entry=entry_price,
            stop=stop_loss,
            rr=signal.risk_reward_ratio
        )
        
        return signal
    
    def _has_bullish_bounce(self, bars: List[Bar]) -> bool:
        """Check if recent bars show bullish bounce"""
        if len(bars) < 3:
            return False
        
        # Last bar should be bullish (close > open)
        last_bar = bars[-1]
        if last_bar.close <= last_bar.open:
            return False
        
        # Previous bar should have lower low (pullback)
        if len(bars) >= 2:
            prev_bar = bars[-2]
            if prev_bar.low >= last_bar.low:
                return False
        
        return True
    
    def _has_bearish_bounce(self, bars: List[Bar]) -> bool:
        """Check if recent bars show bearish bounce"""
        if len(bars) < 3:
            return False
        
        # Last bar should be bearish (close < open)
        last_bar = bars[-1]
        if last_bar.close >= last_bar.open:
            return False
        
        # Previous bar should have higher high (pullback)
        if len(bars) >= 2:
            prev_bar = bars[-2]
            if prev_bar.high <= last_bar.high:
                return False
        
        return True
    
    def _can_generate_signal(self, token: int, timestamp) -> bool:
        """Check if enough time has passed since last signal"""
        if token not in self.last_signal_time:
            return True
        
        time_diff = (timestamp - self.last_signal_time[token]).total_seconds() / 60
        
        return time_diff >= self.min_signal_gap_minutes
    
    def validate(self, context: StrategyContext) -> bool:
        """Validate trend pullback strategy can run"""
        if not super().validate(context):
            return False
        
        # Need sufficient historical data for EMAs
        if len(context.bars_5s) < max(self.ema_slow, self.atr_period) + 10:
            return False
        
        return True
