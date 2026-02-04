"""Iron Condor Options Strategy"""
from datetime import datetime
from typing import List

import structlog

from packages.core.models import Signal, SignalSide
from packages.core.strategies.base import Strategy, StrategyContext

logger = structlog.get_logger(__name__)


class IronCondorStrategy(Strategy):
    """
    Iron Condor Options Strategy
    
    Structure:
    - Sell OTM Call Spread (sell lower strike call, buy higher strike call)
    - Sell OTM Put Spread (sell higher strike put, buy lower strike put)
    
    This creates a profit zone between the two short strikes.
    
    Parameters:
    - call_spread_width: Width of call spread (default: 200)
    - put_spread_width: Width of put spread (default: 200)
    - call_short_strike_offset: Distance from ATM for short call (default: 200)
    - put_short_strike_offset: Distance from ATM for short put (default: 200)
    - max_dte: Maximum days to expiry (default: 20)
    - min_dte: Minimum days to expiry (default: 9)
    - target_profit_pct: Target profit percentage to close (default: 50)
    - max_loss_pct: Maximum loss percentage to close (default: 200)
    - iv_percentile_min: Minimum IV percentile (default: 30)
    - iv_percentile_max: Maximum IV percentile (default: 70)
    """

    def __init__(self, name: str, params: dict):
        super().__init__(name, params)

        self.call_spread_width = params.get("call_spread_width", 200)
        self.put_spread_width = params.get("put_spread_width", 200)
        self.call_short_strike_offset = params.get("call_short_strike_offset", 200)
        self.put_short_strike_offset = params.get("put_short_strike_offset", 200)
        self.max_dte = params.get("max_dte", 20)
        self.min_dte = params.get("min_dte", 9)
        self.target_profit_pct = params.get("target_profit_pct", 50)
        self.max_loss_pct = params.get("max_loss_pct", 200)
        self.iv_percentile_min = params.get("iv_percentile_min", 30)
        self.iv_percentile_max = params.get("iv_percentile_max", 70)

        # State tracking
        self.last_signal_time: dict = {}  # instrument_token -> timestamp
        self.min_signal_gap_days = 1

    def generate_signals(self, context: StrategyContext) -> List[Signal]:
        """Generate Iron Condor signals"""
        if not self.validate(context):
            return []

        # Only trade on indices
        if context.instrument.symbol not in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]:
            return []

        # Need underlying value for strike selection
        if context.underlying_price is None and context.latest_tick is None:
            return []

        # For Iron Condor, we need to construct a 4-leg spread
        # This is complex, so we'll create a simplified signal
        # that represents the entire spread

        # Get ATM and calculate strikes
        # Use provided underlying price if available (from backtest/live chain), else fall back to instrument price
        # (though falling back to instrument price for options strategy is usually wrong unless trading the underlying)
        underlying_value = context.underlying_price if context.underlying_price else context.latest_tick.close

        # Calculate strikes
        call_short_strike = round(underlying_value + self.call_short_strike_offset, 50)
        call_long_strike = call_short_strike + self.call_spread_width

        put_short_strike = round(underlying_value - self.put_short_strike_offset, 50)
        put_long_strike = put_short_strike - self.put_spread_width

        # Check IV percentile
        if context.iv_percentile:
            if context.iv_percentile < self.iv_percentile_min or context.iv_percentile > self.iv_percentile_max:
                logger.debug(
                    f"IV percentile {context.iv_percentile:.1f} outside range [{self.iv_percentile_min}, {self.iv_percentile_max}]"
                )
                return []

        # Avoid too frequent signals
        if not self._can_generate_signal(context.instrument.token, context.timestamp):
            return []

        # Calculate max profit and max loss
        # Max profit = Net credit received
        # Max loss = Width of wider spread - Net credit

        # Estimate credit (simplified - would need actual option prices)
        estimated_credit = (self.call_spread_width + self.put_spread_width) * 0.1  # Rough estimate

        # Max loss is the width of the wider spread minus credit
        max_loss = max(self.call_spread_width, self.put_spread_width) - estimated_credit

        # Create signal representing the Iron Condor
        # Entry price is the net credit received
        entry_price = estimated_credit

        # Stop loss is max loss
        stop_loss = entry_price - max_loss

        # Take profit at 50% of max profit
        take_profit_1 = entry_price + (estimated_credit * 0.5)

        # Full profit target
        take_profit_2 = entry_price + estimated_credit

        signal = Signal(
            strategy_name=self.name,
            timestamp=context.timestamp,
            instrument=context.instrument,
            side=SignalSide.LONG,  # Long the spread (credit received)
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            confidence=0.65,
            rationale=(
                f"Iron Condor: Call {call_short_strike}/{call_long_strike}, "
                f"Put {put_short_strike}/{put_long_strike}, "
                f"Credit: {estimated_credit:.2f}"
            ),
            features={
                "strategy_type": "IRON_CONDOR",
                "call_short_strike": call_short_strike,
                "call_long_strike": call_long_strike,
                "put_short_strike": put_short_strike,
                "put_long_strike": put_long_strike,
                "underlying_value": underlying_value,
                "call_spread_width": self.call_spread_width,
                "put_spread_width": self.put_spread_width,
                "estimated_credit": estimated_credit,
                "max_loss": max_loss,
                "iv_percentile": context.iv_percentile
            }
        )

        signal.risk_amount = max_loss
        signal.reward_amount = estimated_credit

        self.signals_generated += 1
        self.last_signal_time[context.instrument.token] = context.timestamp

        logger.info(
            "Iron Condor signal generated",
            instrument=context.instrument.tradingsymbol,
            call_spread=f"{call_short_strike}/{call_long_strike}",
            put_spread=f"{put_short_strike}/{put_long_strike}",
            credit=estimated_credit,
            max_loss=max_loss,
            rr=signal.risk_reward_ratio
        )

        return [signal]

    def _can_generate_signal(self, token: int, timestamp: datetime) -> bool:
        """Check if enough time has passed since last signal"""
        if token not in self.last_signal_time:
            return True

        time_diff = (timestamp - self.last_signal_time[token]).days

        return time_diff >= self.min_signal_gap_days

    def validate(self, context: StrategyContext) -> bool:
        """Validate Iron Condor strategy can run"""
        if not super().validate(context):
            return False

        # Need underlying value
        has_underlying = context.underlying_price is not None and context.underlying_price > 0
        has_tick = context.latest_tick is not None and context.latest_tick.close > 0

        if not has_underlying and not has_tick:
            return False

        # Check IV percentile if available
        if context.iv_percentile is not None:
            if context.iv_percentile < self.iv_percentile_min or context.iv_percentile > self.iv_percentile_max:
                return False

        return True

