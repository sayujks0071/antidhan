#!/usr/bin/env python3
"""
Clawdbot Optimization Service
Periodically queries Clawdbot for strategy parameter optimizations based on performance data.
"""
import os
import sys
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

# Add services to path
services_path = Path(__file__).parent
if str(services_path) not in sys.path:
    sys.path.insert(0, str(services_path))

try:
    from clawdbot_bridge_service import get_bridge_service
except ImportError:
    logging.warning("Clawdbot bridge service not available")
    get_bridge_service = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ClawdbotOptimization")

class ClawdbotOptimizationService:
    """Service for getting AI-powered strategy parameter optimizations"""
    
    def __init__(self):
        self.bridge = get_bridge_service() if get_bridge_service else None
        self.enabled = os.getenv("CLAWDBOT_ENABLED", "true").lower() == "true"
        self.ai_enabled = os.getenv("CLAWDBOT_AI_ENABLED", "true").lower() == "true"
    
    def collect_strategy_performance(
        self,
        strategy_name: str,
        trade_history: list = None,
        current_params: dict = None
    ) -> Dict[str, Any]:
        """
        Collect performance data for a strategy.
        
        Args:
            strategy_name: Name of the strategy
            trade_history: List of trade dictionaries
            current_params: Current strategy parameters
            
        Returns:
            Dict with performance metrics
        """
        if not trade_history:
            trade_history = []
        
        # Calculate basic metrics
        total_trades = len(trade_history)
        winning_trades = [t for t in trade_history if t.get("pnl", 0) > 0]
        losing_trades = [t for t in trade_history if t.get("pnl", 0) < 0]
        
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        avg_win = sum(t.get("pnl", 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(abs(t.get("pnl", 0)) for t in losing_trades) / len(losing_trades) if losing_trades else 0
        profit_factor = (avg_win * len(winning_trades)) / (avg_loss * len(losing_trades)) if avg_loss > 0 and losing_trades else 0
        
        return {
            "strategy": strategy_name,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "current_params": current_params or {},
            "timestamp": datetime.now().isoformat()
        }
    
    def get_optimization_suggestions(
        self,
        strategy_name: str,
        performance_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get AI suggestions for parameter optimization.
        
        Args:
            strategy_name: Name of the strategy
            performance_data: Performance metrics dictionary
            
        Returns:
            Dict with optimization suggestions
        """
        if not self.enabled or not self.ai_enabled or not self.bridge:
            return {
                "enabled": False,
                "suggestions": {},
                "message": "Clawdbot optimization disabled"
            }
        
        try:
            result = self.bridge.optimize_strategy_parameters(strategy_name, performance_data)
            
            if "error" in result:
                logger.error(f"Error getting optimization suggestions: {result['error']}")
                return {
                    "enabled": True,
                    "error": result["error"],
                    "suggestions": {}
                }
            
            suggestions = result.get("suggestions", {})
            return {
                "enabled": True,
                "strategy": strategy_name,
                "suggestions": suggestions,
                "expected_impact": result.get("expected_impact", ""),
                "confidence": result.get("confidence", 0.5),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error in get_optimization_suggestions: {e}")
            return {
                "enabled": True,
                "error": str(e),
                "suggestions": {}
            }
    
    def apply_optimization(
        self,
        strategy_name: str,
        suggestions: Dict[str, Any],
        auto_apply: bool = False,
        min_confidence: float = 0.7
    ) -> Dict[str, Any]:
        """
        Apply optimization suggestions (with approval or auto-apply).
        
        Args:
            strategy_name: Name of the strategy
            suggestions: Optimization suggestions dictionary
            auto_apply: Whether to auto-apply if confidence is high
            min_confidence: Minimum confidence for auto-apply
            
        Returns:
            Dict with application status
        """
        if not suggestions or not suggestions.get("suggestions"):
            return {
                "applied": False,
                "reason": "No suggestions available"
            }
        
        confidence = suggestions.get("confidence", 0.0)
        
        if auto_apply and confidence >= min_confidence:
            # Auto-apply high-confidence suggestions
            logger.info(f"Auto-applying optimization for {strategy_name} (confidence: {confidence:.2f})")
            return {
                "applied": True,
                "method": "auto",
                "confidence": confidence,
                "suggestions": suggestions.get("suggestions", {})
            }
        else:
            # Require manual approval
            logger.info(f"Optimization suggestions for {strategy_name} require manual approval")
            return {
                "applied": False,
                "method": "manual",
                "confidence": confidence,
                "suggestions": suggestions.get("suggestions", {}),
                "message": "Manual approval required"
            }


# Singleton instance
_optimization_service_instance: Optional[ClawdbotOptimizationService] = None

def get_optimization_service() -> ClawdbotOptimizationService:
    """Get or create singleton optimization service instance"""
    global _optimization_service_instance
    if _optimization_service_instance is None:
        _optimization_service_instance = ClawdbotOptimizationService()
    return _optimization_service_instance
