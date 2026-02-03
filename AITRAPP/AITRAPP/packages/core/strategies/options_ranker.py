"""Options Ranker Strategy"""
from typing import List, Optional

import structlog

from packages.core.models import Signal, SignalSide
from packages.core.strategies.base import Strategy, StrategyContext

logger = structlog.get_logger(__name__)


class OptionsRankerStrategy(Strategy):
    """
    Options Ranker Strategy
    
    Ranks and trades option spreads based on:
    - IV Percentile (IVP): Prefer selling premium when IVP is high, buying when low
    - Liquidity: Bid-ask spread, OI, volume
    - Directional bias: From underlying trend
    - Risk-reward profile
    
    Strategy Types:
    - DEBIT_SPREAD: Buy ITM, sell OTM (directional, limited risk)
    - CREDIT_SPREAD: Sell OTM, buy further OTM (income, limited risk)
    - DIRECTIONAL: Single option leg (long call/put)
    
    Parameters:
    - strategy_type: DEBIT_SPREAD | CREDIT_SPREAD | DIRECTIONAL
    - ivp_min: Minimum IV percentile (for selling premium)
    - ivp_max: Maximum IV percentile (for buying premium)
    - liquidity_score_min: Minimum liquidity score (0-1)
    - max_spread_legs: Maximum number of legs (default: 2)
    - rr_min: Minimum risk-reward ratio
    """

    def __init__(self, name: str, params: dict):
        super().__init__(name, params)

        self.strategy_type = params.get("strategy_type", "DEBIT_SPREAD")
        self.ivp_min = params.get("ivp_min", 30)
        self.ivp_max = params.get("ivp_max", 70)
        self.liquidity_score_min = params.get("liquidity_score_min", 0.7)
        self.max_spread_legs = params.get("max_spread_legs", 2)
        self.rr_min = params.get("rr_min", 1.5)

        # Options data cache (would be fetched from market)
        self.options_cache: dict = {}  # underlying_token -> list of option instruments

    def generate_signals(self, context: StrategyContext) -> List[Signal]:
        """Generate options trading signals"""
        if not self.validate(context):
            return []

        # Only trade options on indices for now
        if context.instrument.symbol not in ["NIFTY", "BANKNIFTY", "FINNIFTY"]:
            return []

        # Check IV percentile
        if context.iv_percentile is None:
            logger.debug("IV percentile not available", instrument=context.instrument.tradingsymbol)
            return []

        ivp = context.iv_percentile

        signals = []

        if self.strategy_type == "DEBIT_SPREAD":
            signal = self._generate_debit_spread(context, ivp)
            if signal:
                signals.append(signal)

        elif self.strategy_type == "CREDIT_SPREAD":
            signal = self._generate_credit_spread(context, ivp)
            if signal:
                signals.append(signal)

        elif self.strategy_type == "DIRECTIONAL":
            signal = self._generate_directional(context, ivp)
            if signal:
                signals.append(signal)

        return signals

    def _generate_debit_spread(self, context: StrategyContext, ivp: float) -> Optional[Signal]:
        """
        Generate debit spread signal.
        
        Buy ITM option, sell OTM option (same expiry, same type).
        Works best when IVP is low (cheaper premium).
        """
        # Prefer debit spreads when IV is not too high
        if ivp > self.ivp_max:
            logger.debug("IVP too high for debit spread", ivp=ivp)
            return None

        # Determine direction from underlying trend
        direction = self._get_directional_bias(context)

        if direction is None:
            return None

        # In production, fetch actual options chain and select strikes
        # For now, create placeholder signal

        current_price = context.latest_tick.last_price

        if direction == "BULLISH":
            # Bull call spread: Buy ITM call, sell OTM call
            buy_strike = current_price * 0.98  # ITM
            sell_strike = current_price * 1.02  # OTM

            # Estimate spread cost and max profit
            spread_cost = 100  # Placeholder
            max_profit = (sell_strike - buy_strike) - spread_cost

            if max_profit / spread_cost < self.rr_min:
                return None

            signal = Signal(
                strategy_name=self.name,
                timestamp=context.timestamp,
                instrument=context.instrument,
                side=SignalSide.LONG,
                entry_price=spread_cost,
                stop_loss=0,  # Max loss is spread cost
                take_profit_1=spread_cost + (max_profit * 0.6),
                take_profit_2=spread_cost + max_profit,
                confidence=0.65,
                rationale=f"Bull call spread on {context.instrument.symbol}, IVP={ivp:.1f}",
                features={
                    "strategy_type": "DEBIT_SPREAD",
                    "spread_type": "BULL_CALL",
                    "buy_strike": buy_strike,
                    "sell_strike": sell_strike,
                    "ivp": ivp,
                    "max_loss": spread_cost,
                    "max_profit": max_profit
                }
            )

        else:  # BEARISH
            # Bear put spread: Buy ITM put, sell OTM put
            buy_strike = current_price * 1.02  # ITM
            sell_strike = current_price * 0.98  # OTM

            spread_cost = 100  # Placeholder
            max_profit = (buy_strike - sell_strike) - spread_cost

            if max_profit / spread_cost < self.rr_min:
                return None

            signal = Signal(
                strategy_name=self.name,
                timestamp=context.timestamp,
                instrument=context.instrument,
                side=SignalSide.SHORT,
                entry_price=spread_cost,
                stop_loss=0,
                take_profit_1=spread_cost + (max_profit * 0.6),
                take_profit_2=spread_cost + max_profit,
                confidence=0.65,
                rationale=f"Bear put spread on {context.instrument.symbol}, IVP={ivp:.1f}",
                features={
                    "strategy_type": "DEBIT_SPREAD",
                    "spread_type": "BEAR_PUT",
                    "buy_strike": buy_strike,
                    "sell_strike": sell_strike,
                    "ivp": ivp,
                    "max_loss": spread_cost,
                    "max_profit": max_profit
                }
            )

        signal.risk_amount = spread_cost
        signal.reward_amount = max_profit

        self.signals_generated += 1

        logger.info(
            "Debit spread signal",
            instrument=context.instrument.tradingsymbol,
            type=signal.features["spread_type"],
            rr=signal.risk_reward_ratio
        )

        return signal

    def _generate_credit_spread(self, context: StrategyContext, ivp: float) -> Optional[Signal]:
        """
        Generate credit spread signal.
        
        Sell OTM option, buy further OTM option (same expiry, same type).
        Works best when IVP is high (expensive premium to sell).
        """
        # Prefer credit spreads when IV is high
        if ivp < self.ivp_min:
            logger.debug("IVP too low for credit spread", ivp=ivp)
            return None

        # Determine direction (opposite for credit spreads)
        direction = self._get_directional_bias(context)

        if direction is None:
            return None

        current_price = context.latest_tick.last_price

        if direction == "BEARISH":
            # Bear call spread: Sell OTM call, buy further OTM call
            sell_strike = current_price * 1.02  # OTM
            buy_strike = current_price * 1.05  # Further OTM

            spread_credit = 80  # Placeholder (premium collected)
            max_loss = (buy_strike - sell_strike) - spread_credit

            if spread_credit / max_loss < (self.rr_min / 2):  # Credit spreads have different RR profile
                return None

            signal = Signal(
                strategy_name=self.name,
                timestamp=context.timestamp,
                instrument=context.instrument,
                side=SignalSide.SHORT,
                entry_price=spread_credit,
                stop_loss=spread_credit + max_loss,
                take_profit_1=spread_credit * 0.5,  # Close at 50% profit
                take_profit_2=spread_credit * 0.8,  # Close at 80% profit
                confidence=0.70,
                rationale=f"Bear call spread on {context.instrument.symbol}, IVP={ivp:.1f}",
                features={
                    "strategy_type": "CREDIT_SPREAD",
                    "spread_type": "BEAR_CALL",
                    "sell_strike": sell_strike,
                    "buy_strike": buy_strike,
                    "ivp": ivp,
                    "max_loss": max_loss,
                    "max_profit": spread_credit
                }
            )

        else:  # BULLISH
            # Bull put spread: Sell OTM put, buy further OTM put
            sell_strike = current_price * 0.98  # OTM
            buy_strike = current_price * 0.95  # Further OTM

            spread_credit = 80  # Placeholder
            max_loss = (sell_strike - buy_strike) - spread_credit

            if spread_credit / max_loss < (self.rr_min / 2):
                return None

            signal = Signal(
                strategy_name=self.name,
                timestamp=context.timestamp,
                instrument=context.instrument,
                side=SignalSide.LONG,
                entry_price=spread_credit,
                stop_loss=spread_credit + max_loss,
                take_profit_1=spread_credit * 0.5,
                take_profit_2=spread_credit * 0.8,
                confidence=0.70,
                rationale=f"Bull put spread on {context.instrument.symbol}, IVP={ivp:.1f}",
                features={
                    "strategy_type": "CREDIT_SPREAD",
                    "spread_type": "BULL_PUT",
                    "sell_strike": sell_strike,
                    "buy_strike": buy_strike,
                    "ivp": ivp,
                    "max_loss": max_loss,
                    "max_profit": spread_credit
                }
            )

        signal.risk_amount = max_loss
        signal.reward_amount = spread_credit

        self.signals_generated += 1

        logger.info(
            "Credit spread signal",
            instrument=context.instrument.tradingsymbol,
            type=signal.features["spread_type"],
            rr=signal.risk_reward_ratio
        )

        return signal

    def _generate_directional(self, context: StrategyContext, ivp: float) -> Optional[Signal]:
        """
        Generate directional option signal (single leg).
        
        Buy ATM or slightly OTM option based on trend.
        """
        direction = self._get_directional_bias(context)

        if direction is None:
            return None

        # For directional plays, prefer lower IV (cheaper entry)
        if ivp > self.ivp_max:
            return None

        current_price = context.latest_tick.last_price

        if direction == "BULLISH":
            strike = current_price * 1.01  # Slightly OTM call
            option_premium = 50  # Placeholder
            target_price = option_premium * (1 + self.rr_min)

            signal = Signal(
                strategy_name=self.name,
                timestamp=context.timestamp,
                instrument=context.instrument,
                side=SignalSide.LONG,
                entry_price=option_premium,
                stop_loss=option_premium * 0.5,  # 50% stop
                take_profit_1=option_premium * 1.5,
                take_profit_2=target_price,
                confidence=0.60,
                rationale=f"Long call on {context.instrument.symbol}, IVP={ivp:.1f}",
                features={
                    "strategy_type": "DIRECTIONAL",
                    "option_type": "CALL",
                    "strike": strike,
                    "ivp": ivp
                }
            )

        else:  # BEARISH
            strike = current_price * 0.99  # Slightly OTM put
            option_premium = 50  # Placeholder
            target_price = option_premium * (1 + self.rr_min)

            signal = Signal(
                strategy_name=self.name,
                timestamp=context.timestamp,
                instrument=context.instrument,
                side=SignalSide.SHORT,
                entry_price=option_premium,
                stop_loss=option_premium * 0.5,
                take_profit_1=option_premium * 1.5,
                take_profit_2=target_price,
                confidence=0.60,
                rationale=f"Long put on {context.instrument.symbol}, IVP={ivp:.1f}",
                features={
                    "strategy_type": "DIRECTIONAL",
                    "option_type": "PUT",
                    "strike": strike,
                    "ivp": ivp
                }
            )

        signal.risk_amount = option_premium * 0.5
        signal.reward_amount = option_premium * self.rr_min

        self.signals_generated += 1

        return signal

    def _get_directional_bias(self, context: StrategyContext) -> Optional[str]:
        """
        Determine directional bias from underlying price action.
        
        Returns:
            "BULLISH", "BEARISH", or None
        """
        if not context.bars_5s or len(context.bars_5s) < 20:
            return None

        latest_bar = context.bars_5s[-1]

        # Use EMA and Supertrend for direction
        if latest_bar.ema_fast and latest_bar.ema_slow:
            if latest_bar.ema_fast > latest_bar.ema_slow:
                # Check Supertrend confirmation
                if latest_bar.supertrend_direction == 1:
                    return "BULLISH"
            elif latest_bar.ema_fast < latest_bar.ema_slow:
                if latest_bar.supertrend_direction == -1:
                    return "BEARISH"

        # Fallback: simple momentum
        bars = context.bars_5s[-20:]
        avg_close = sum([b.close for b in bars]) / len(bars)
        current_price = context.latest_tick.last_price

        if current_price > avg_close * 1.005:
            return "BULLISH"
        elif current_price < avg_close * 0.995:
            return "BEARISH"

        return None

    def validate(self, context: StrategyContext) -> bool:
        """Validate options strategy can run"""
        if not super().validate(context):
            return False

        # Need IV data
        if context.iv_percentile is None:
            return False

        # Only trade during regular hours, not near expiry
        # (In production, check days to expiry)

        return True
