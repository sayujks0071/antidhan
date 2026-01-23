"""Signal ranking and prioritization engine"""
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import structlog

from packages.core.config import RankingConfig
from packages.core.models import Bar, Instrument, RankedOpportunity, Signal, Tick

logger = structlog.get_logger(__name__)


@dataclass
class FeatureVector:
    """Normalized feature vector for ranking"""
    momentum: float = 0.0
    trend: float = 0.0
    liquidity: float = 0.0
    regime: float = 0.0
    rr: float = 0.0
    
    # Raw metrics (for explainability)
    raw_momentum: float = 0.0
    raw_trend: float = 0.0
    raw_liquidity: float = 0.0
    raw_regime: float = 0.0
    raw_rr: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return {
            "momentum": self.momentum,
            "trend": self.trend,
            "liquidity": self.liquidity,
            "regime": self.regime,
            "rr": self.rr
        }


class SignalRanker:
    """
    Ranks trading signals using feature normalization and weighted fusion.
    
    Features:
    - Momentum: Price momentum using RSI, rate of change
    - Trend: Trend strength using ADX, EMA alignment
    - Liquidity: Volume, bid-ask spread, OI for options
    - Regime: IV percentile, OI changes, market conditions
    - Risk-Reward: Signal's R:R ratio
    
    Penalties:
    - Illiquid instruments
    - Trading into news events
    - Far from session VWAP
    """
    
    def __init__(self, config: RankingConfig):
        self.config = config
        
        # Feature history for z-score normalization
        self.feature_history: Dict[str, List[float]] = {
            "momentum": [],
            "trend": [],
            "liquidity": [],
            "regime": [],
            "rr": []
        }
        
        self.history_window = 100
    
    def rank_signals(
        self,
        signals: List[Signal],
        market_data: Dict[int, tuple[Tick, List[Bar]]],
        event_flags: Dict[int, bool] = None
    ) -> List[RankedOpportunity]:
        """
        Rank signals and return top opportunities.
        
        Args:
            signals: List of trading signals
            market_data: Dict of token -> (latest_tick, bars)
            event_flags: Dict of token -> has_news_event
        
        Returns:
            List of RankedOpportunity sorted by score (highest first)
        """
        if not signals:
            return []
        
        if event_flags is None:
            event_flags = {}
        
        opportunities = []
        
        for signal in signals:
            # Get market data
            tick_bars = market_data.get(signal.instrument.token)
            if not tick_bars:
                logger.warning(
                    "No market data for signal",
                    instrument=signal.instrument.tradingsymbol
                )
                continue
            
            tick, bars = tick_bars
            
            # Compute features
            features = self._compute_features(signal, tick, bars)
            
            # Calculate base score
            base_score = self._calculate_score(features)
            
            # Apply penalties
            penalties = {}
            final_score = base_score
            
            # Liquidity penalty
            if features.liquidity < 0.5:
                penalty = 1.0 - self.config.penalties["illiquid_mult"]
                penalties["illiquid"] = penalty
                final_score *= self.config.penalties["illiquid_mult"]
            
            # News event penalty
            if event_flags.get(signal.instrument.token, False):
                penalty = 1.0 - self.config.penalties["news_event_mult"]
                penalties["news_event"] = penalty
                final_score *= self.config.penalties["news_event_mult"]
            
            # Far from VWAP penalty
            if bars and bars[-1].vwap:
                vwap = bars[-1].vwap
                distance_pct = abs(signal.entry_price - vwap) / vwap * 100
                if distance_pct > 1.0:  # More than 1% from VWAP
                    penalty = 1.0 - self.config.penalties["far_from_vwap_mult"]
                    penalties["far_from_vwap"] = penalty
                    final_score *= self.config.penalties["far_from_vwap_mult"]
            
            # Create ranked opportunity
            opportunity = RankedOpportunity(
                signal=signal,
                score=final_score,
                rank=0,  # Will be assigned after sorting
                feature_scores=features.to_dict(),
                penalties_applied=penalties,
                liquidity_score=features.liquidity,
                avg_volume=self._calculate_avg_volume(bars) if bars else 0,
                regime_score=features.regime,
                iv_percentile=signal.features.get("ivp")
            )
            
            opportunities.append(opportunity)
        
        # Sort by score (descending)
        opportunities.sort(key=lambda x: x.score, reverse=True)
        
        # Assign ranks
        for i, opp in enumerate(opportunities):
            opp.rank = i + 1
        
        # Return top N
        top_n = self.config.top_n
        top_opportunities = opportunities[:top_n]
        
        if top_opportunities:
            logger.info(
                "Ranked signals",
                total=len(signals),
                top_n=len(top_opportunities),
                best_score=top_opportunities[0].score
            )
            
            # Log top opportunity details
            best = top_opportunities[0]
            logger.info(
                "Top opportunity",
                instrument=best.signal.instrument.tradingsymbol,
                strategy=best.signal.strategy_name,
                side=best.signal.side,
                score=best.score,
                features=best.feature_scores,
                penalties=best.penalties_applied
            )
        
        return top_opportunities
    
    def _compute_features(
        self,
        signal: Signal,
        tick: Tick,
        bars: List[Bar]
    ) -> FeatureVector:
        """Compute and normalize features for a signal"""
        features = FeatureVector()
        
        # 1. Momentum
        features.raw_momentum = self._calculate_momentum(bars, signal)
        features.momentum = self._normalize_feature("momentum", features.raw_momentum)
        
        # 2. Trend
        features.raw_trend = self._calculate_trend(bars)
        features.trend = self._normalize_feature("trend", features.raw_trend)
        
        # 3. Liquidity
        features.raw_liquidity = self._calculate_liquidity(tick, bars)
        features.liquidity = self._normalize_feature("liquidity", features.raw_liquidity)
        
        # 4. Regime
        features.raw_regime = self._calculate_regime(signal, bars)
        features.regime = self._normalize_feature("regime", features.raw_regime)
        
        # 5. Risk-Reward
        features.raw_rr = signal.risk_reward_ratio
        features.rr = self._normalize_feature("rr", features.raw_rr)
        
        return features
    
    def _calculate_momentum(self, bars: List[Bar], signal: Signal) -> float:
        """
        Calculate momentum score.
        
        Uses RSI, rate of change, and signal confidence.
        Returns: 0.0 to 1.0
        """
        if not bars or len(bars) < 20:
            return 0.5
        
        latest_bar = bars[-1]
        score = 0.0
        count = 0
        
        # RSI component
        if latest_bar.rsi is not None:
            # Transform RSI to 0-1 score
            # For LONG: prefer RSI 40-60 (neutral to slightly bullish)
            # For SHORT: prefer RSI 40-60 (neutral to slightly bearish)
            rsi = latest_bar.rsi
            if signal.side.value == "LONG":
                if 40 <= rsi <= 60:
                    score += 0.8
                elif 30 <= rsi < 40:
                    score += 0.6
                elif 60 < rsi <= 70:
                    score += 0.6
                else:
                    score += 0.3
            else:  # SHORT
                if 40 <= rsi <= 60:
                    score += 0.8
                elif 30 <= rsi < 40:
                    score += 0.6
                elif 60 < rsi <= 70:
                    score += 0.6
                else:
                    score += 0.3
            count += 1
        
        # Rate of change (recent 20 bars)
        if len(bars) >= 20:
            roc = (bars[-1].close - bars[-20].close) / bars[-20].close
            roc_abs = abs(roc)
            
            # Prefer moderate momentum (0.5% - 2%)
            if 0.005 <= roc_abs <= 0.02:
                score += 0.8
            elif roc_abs < 0.005:
                score += 0.5  # Too weak
            else:
                score += 0.6  # Too strong
            count += 1
        
        # Signal confidence
        score += signal.confidence
        count += 1
        
        return score / count if count > 0 else 0.5
    
    def _calculate_trend(self, bars: List[Bar]) -> float:
        """
        Calculate trend strength score.
        
        Uses ADX and EMA alignment.
        Returns: 0.0 to 1.0
        """
        if not bars or len(bars) < 50:
            return 0.5
        
        latest_bar = bars[-1]
        score = 0.0
        count = 0
        
        # ADX component (trend strength)
        if latest_bar.adx is not None:
            adx = latest_bar.adx
            if adx >= 25:
                score += 1.0  # Strong trend
            elif adx >= 20:
                score += 0.7
            elif adx >= 15:
                score += 0.5
            else:
                score += 0.3  # Weak trend
            count += 1
        
        # EMA alignment
        if latest_bar.ema_fast and latest_bar.ema_slow:
            separation_pct = abs(latest_bar.ema_fast - latest_bar.ema_slow) / latest_bar.ema_slow
            
            if separation_pct >= 0.01:  # 1% separation
                score += 1.0
            elif separation_pct >= 0.005:
                score += 0.7
            else:
                score += 0.4
            count += 1
        
        # Supertrend alignment
        if latest_bar.supertrend_direction is not None:
            # Just having a defined direction is positive
            score += 0.7
            count += 1
        
        return score / count if count > 0 else 0.5
    
    def _calculate_liquidity(self, tick: Tick, bars: List[Bar]) -> float:
        """
        Calculate liquidity score.
        
        Uses bid-ask spread, volume.
        Returns: 0.0 to 1.0
        """
        score = 0.0
        count = 0
        
        # Bid-ask spread
        spread_pct = tick.spread_pct
        if spread_pct <= 0.1:
            score += 1.0  # Excellent
        elif spread_pct <= 0.3:
            score += 0.8
        elif spread_pct <= 0.5:
            score += 0.6
        else:
            score += 0.3  # Poor
        count += 1
        
        # Volume (compare to recent average)
        if bars and len(bars) >= 20:
            avg_volume = self._calculate_avg_volume(bars)
            current_volume = bars[-1].volume if bars else 0
            
            if avg_volume > 0:
                volume_ratio = current_volume / avg_volume
                if volume_ratio >= 1.5:
                    score += 1.0  # High volume
                elif volume_ratio >= 1.0:
                    score += 0.8
                elif volume_ratio >= 0.7:
                    score += 0.6
                else:
                    score += 0.4  # Low volume
                count += 1
        
        # Depth (bid/ask quantities)
        depth_score = min((tick.bid_quantity + tick.ask_quantity) / 1000, 1.0)
        score += depth_score
        count += 1
        
        return score / count if count > 0 else 0.5
    
    def _calculate_regime(self, signal: Signal, bars: List[Bar]) -> float:
        """
        Calculate market regime score.
        
        Uses IV percentile, OI trends for options.
        Returns: 0.0 to 1.0
        """
        score = 0.0
        count = 0
        
        # IV percentile (from signal features)
        ivp = signal.features.get("ivp")
        if ivp is not None:
            # Prefer moderate IV (30-70)
            if 30 <= ivp <= 70:
                score += 0.9
            elif 20 <= ivp < 30 or 70 < ivp <= 80:
                score += 0.7
            else:
                score += 0.5
            count += 1
        
        # OI change (for options/futures)
        oi_change = signal.features.get("oi_change_pct")
        if oi_change is not None:
            # Increasing OI is generally positive
            if oi_change > 10:
                score += 0.9
            elif oi_change > 5:
                score += 0.7
            elif oi_change > 0:
                score += 0.6
            else:
                score += 0.4
            count += 1
        
        # Recent volatility stability
        if bars and len(bars) >= 20:
            recent_atr_values = [b.atr for b in bars[-20:] if b.atr is not None]
            if len(recent_atr_values) >= 10:
                atr_std = np.std(recent_atr_values)
                atr_mean = np.mean(recent_atr_values)
                
                if atr_mean > 0:
                    atr_cv = atr_std / atr_mean  # Coefficient of variation
                    
                    # Prefer stable volatility
                    if atr_cv < 0.2:
                        score += 0.9
                    elif atr_cv < 0.4:
                        score += 0.7
                    else:
                        score += 0.5
                    count += 1
        
        return score / count if count > 0 else 0.5
    
    def _calculate_avg_volume(self, bars: List[Bar]) -> float:
        """Calculate average volume from recent bars"""
        if not bars:
            return 0.0
        
        volumes = [b.volume for b in bars[-20:]]
        return sum(volumes) / len(volumes) if volumes else 0.0
    
    def _normalize_feature(self, feature_name: str, value: float) -> float:
        """
        Normalize feature using z-score with rolling window.
        
        Clips to [0, 1] range for stability.
        """
        # Add to history
        if feature_name in self.feature_history:
            self.feature_history[feature_name].append(value)
            if len(self.feature_history[feature_name]) > self.history_window:
                self.feature_history[feature_name].pop(0)
        
        # Need at least 10 samples for normalization
        history = self.feature_history.get(feature_name, [])
        if len(history) < 10:
            # Return raw value clipped to [0, 1]
            return max(0.0, min(1.0, value))
        
        # Z-score normalization
        mean = np.mean(history)
        std = np.std(history)
        
        if std > 0:
            z_score = (value - mean) / std
            # Transform to [0, 1] using sigmoid-like function
            normalized = 1 / (1 + np.exp(-z_score))
        else:
            normalized = 0.5
        
        return max(0.0, min(1.0, normalized))
    
    def _calculate_score(self, features: FeatureVector) -> float:
        """
        Calculate weighted score from features.
        
        Uses weights from config.
        """
        weights = self.config.weights
        
        score = (
            features.momentum * weights["momentum"] +
            features.trend * weights["trend"] +
            features.liquidity * weights["liquidity"] +
            features.regime * weights["regime"] +
            features.rr * weights["rr"]
        )
        
        return score
    
    def explain_ranking(self, opportunity: RankedOpportunity) -> Dict:
        """
        Generate explainability report for a ranked opportunity.
        
        Returns:
            Dict with feature contributions and reasoning
        """
        weights = self.config.weights
        
        contributions = {}
        for feature, score in opportunity.feature_scores.items():
            contribution = score * weights.get(feature, 0.0)
            contributions[feature] = {
                "score": score,
                "weight": weights.get(feature, 0.0),
                "contribution": contribution
            }
        
        explanation = {
            "rank": opportunity.rank,
            "final_score": opportunity.score,
            "base_score": sum([c["contribution"] for c in contributions.values()]),
            "features": contributions,
            "penalties": opportunity.penalties_applied,
            "signal": {
                "strategy": opportunity.signal.strategy_name,
                "instrument": opportunity.signal.instrument.tradingsymbol,
                "side": opportunity.signal.side.value,
                "entry": opportunity.signal.entry_price,
                "stop": opportunity.signal.stop_loss,
                "rr": opportunity.signal.risk_reward_ratio,
                "rationale": opportunity.signal.rationale
            }
        }
        
        return explanation

