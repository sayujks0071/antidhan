"""Opening Range Breakout (ORB) Strategy with Trend Filter"""
import structlog
import pandas as pd
from typing import List

from packages.core.models import Signal, SignalSide
from packages.core.strategies.base import StrategyContext
from packages.core.strategies.orb import ORBStrategy

logger = structlog.get_logger(__name__)

class ORBTrendStrategy(ORBStrategy):
    """
    ORB Strategy with Trend Filter (EMA)

    Inherits from ORBStrategy and adds a trend confirmation using EMA.
    - Long signals only if price > EMA
    - Short signals only if price < EMA
    """

    def __init__(self, name: str, params: dict):
        super().__init__(name, params)
        self.ema_period = params.get("ema_period", 100)

    def generate_signals(self, context: StrategyContext) -> List[Signal]:
        # Get signals from base strategy
        signals = super().generate_signals(context)

        if not signals:
            return []

        # Calculate EMA
        if not context.bars_5s or len(context.bars_5s) < self.ema_period:
            # Not enough data for trend, reject signal
            logger.warning(f"Not enough data for EMA calculation. Needed {self.ema_period}, got {len(context.bars_5s) if context.bars_5s else 0}")
            return []

        closes = pd.Series([b.close for b in context.bars_5s])
        ema = closes.ewm(span=self.ema_period, adjust=False).mean().iloc[-1]

        filtered_signals = []
        for signal in signals:
            if signal.side == SignalSide.LONG:
                if signal.entry_price > ema:
                    signal.features["trend_ema"] = ema
                    signal.rationale += f" | Trend confirmed (Price {signal.entry_price:.2f} > EMA {ema:.2f})"
                    filtered_signals.append(signal)
                else:
                    logger.info("ORB LONG signal rejected by trend filter",
                                price=signal.entry_price, ema=ema)
            elif signal.side == SignalSide.SHORT:
                if signal.entry_price < ema:
                    signal.features["trend_ema"] = ema
                    signal.rationale += f" | Trend confirmed (Price {signal.entry_price:.2f} < EMA {ema:.2f})"
                    filtered_signals.append(signal)
                else:
                    logger.info("ORB SHORT signal rejected by trend filter",
                                price=signal.entry_price, ema=ema)

        return filtered_signals
