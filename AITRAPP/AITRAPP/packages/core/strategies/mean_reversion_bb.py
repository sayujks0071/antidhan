"""Mean Reversion Bollinger Bands Strategy"""
from typing import List

import pandas as pd
import structlog

from packages.core.models import Signal, SignalSide
from packages.core.strategies.base import Strategy, StrategyContext

logger = structlog.get_logger(__name__)

class MeanReversionBBStrategy(Strategy):
    """
    Mean Reversion Strategy using Bollinger Bands.

    Logic:
    - Long when price touches or crosses below Lower Band
    - Short when price touches or crosses above Upper Band
    - Exit when price touches Moving Average (Mean) - NOT IMPLEMENTED in Signal,
      this strategy generates Entry signals. Exit logic handled by execution engine or TP/SL.
    """

    def __init__(self, name: str, params: dict):
        super().__init__(name, params)
        self.period = params.get("period", 20)
        self.std_dev = params.get("std_dev", 2.0)
        self.min_bars = params.get("min_bars", 30)  # Need enough data for calculation

    def generate_signals(self, context: StrategyContext) -> List[Signal]:
        # Basic validation
        if not self.validate(context):
            return []

        # Check sufficient data
        if not context.bars_5s or len(context.bars_5s) < self.period:
            logger.warning(
                "Insufficient data for BB calculation",
                strategy=self.name,
                required=self.period,
                available=len(context.bars_5s) if context.bars_5s else 0
            )
            return []

        # Prepare dataframe
        bars = context.bars_5s
        df = pd.DataFrame([{
            'close': b.close,
            'high': b.high,
            'low': b.low
        } for b in bars])

        # Calculate Bollinger Bands
        df['sma'] = df['close'].rolling(window=self.period).mean()
        df['std'] = df['close'].rolling(window=self.period).std()
        df['upper_bb'] = df['sma'] + (df['std'] * self.std_dev)
        df['lower_bb'] = df['sma'] - (df['std'] * self.std_dev)

        current_close = df['close'].iloc[-1]
        current_upper = df['upper_bb'].iloc[-1]
        current_lower = df['lower_bb'].iloc[-1]

        # Check valid calculation
        if pd.isna(current_upper) or pd.isna(current_lower):
            return []

        signals = []

        # Long Logic: Price <= Lower Band
        if current_close <= current_lower:
            # Check for existing positions or other constraints if needed

            signal = Signal(
                strategy_name=self.name,
                timestamp=context.timestamp,
                instrument=context.instrument,
                side=SignalSide.LONG,
                entry_price=current_close,
                stop_loss=current_close * 0.99,  # 1% SL default
                take_profit_1=df['sma'].iloc[-1], # Target Mean
                take_profit_2=current_upper,      # Target Upper Band
                confidence=0.8,
                rationale=f"Price {current_close:.2f} below Lower BB {current_lower:.2f}",
                features={
                    "bb_lower": current_lower,
                    "bb_upper": current_upper,
                    "bb_sma": df['sma'].iloc[-1]
                }
            )
            signals.append(signal)
            logger.info("Generated LONG signal", strategy=self.name, price=current_close, bb_lower=current_lower)

        # Short Logic: Price >= Upper Band
        elif current_close >= current_upper:
            signal = Signal(
                strategy_name=self.name,
                timestamp=context.timestamp,
                instrument=context.instrument,
                side=SignalSide.SHORT,
                entry_price=current_close,
                stop_loss=current_close * 1.01,  # 1% SL default
                take_profit_1=df['sma'].iloc[-1], # Target Mean
                take_profit_2=current_lower,      # Target Lower Band
                confidence=0.8,
                rationale=f"Price {current_close:.2f} above Upper BB {current_upper:.2f}",
                features={
                    "bb_lower": current_lower,
                    "bb_upper": current_upper,
                    "bb_sma": df['sma'].iloc[-1]
                }
            )
            signals.append(signal)
            logger.info("Generated SHORT signal", strategy=self.name, price=current_close, bb_upper=current_upper)

        return signals
