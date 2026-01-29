#!/usr/bin/env python3
"""
Clawdbot Adapter for Trading Strategies
Provides easy-to-use functions for strategies to interact with Clawdbot AI.
"""
import os
import sys
import logging
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

# Add services to path
services_path = Path(__file__).parent.parent.parent / 'services'
if str(services_path) not in sys.path:
    sys.path.insert(0, str(services_path))

try:
    from clawdbot_bridge_service import get_bridge_service
except ImportError:
    logging.warning("Clawdbot bridge service not available")
    get_bridge_service = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ClawdbotAdapter")

# Check if Clawdbot is enabled
CLAWDBOT_ENABLED = os.getenv("CLAWDBOT_ENABLED", "true").lower() == "true"

def _run_async(coro):
    """Run async function synchronously"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

def get_ai_market_context(symbol: str, exchange: str = "NSE", timeframe: str = "5m") -> Dict[str, Any]:
    """
    Get AI analysis of market conditions for a symbol.
    
    Args:
        symbol: Trading symbol
        exchange: Exchange name (NSE, MCX, etc.)
        timeframe: Timeframe for analysis (5m, 15m, 1h, D)
        
    Returns:
        Dict with market analysis including regime, sentiment, recommendations
    """
    if not CLAWDBOT_ENABLED or get_bridge_service is None:
        logger.debug("Clawdbot disabled, returning empty context")
        return {
            "enabled": False,
            "regime": "UNKNOWN",
            "sentiment": "NEUTRAL",
            "confidence": 0.0
        }
    
    try:
        bridge = get_bridge_service()
        result = _run_async(bridge.get_market_analysis(symbol, exchange, timeframe))
        
        if "error" in result:
            logger.warning(f"Error getting AI market context: {result['error']}")
            return {
                "enabled": True,
                "error": result["error"],
                "regime": "UNKNOWN",
                "sentiment": "NEUTRAL",
                "confidence": 0.0
            }
        
        # Extract key information from analysis
        analysis = result.get("analysis", {})
        return {
            "enabled": True,
            "symbol": symbol,
            "exchange": exchange,
            "regime": analysis.get("regime", "UNKNOWN"),
            "trend_strength": analysis.get("trend_strength", 50),
            "volatility": analysis.get("volatility", "MEDIUM"),
            "sentiment": analysis.get("recommendation", "NEUTRAL"),
            "confidence": analysis.get("confidence", 50) / 100.0,
            "support_levels": analysis.get("support_levels", []),
            "resistance_levels": analysis.get("resistance_levels", []),
            "full_analysis": result
        }
    except Exception as e:
        logger.error(f"Error in get_ai_market_context: {e}")
        return {
            "enabled": True,
            "error": str(e),
            "regime": "UNKNOWN",
            "sentiment": "NEUTRAL",
            "confidence": 0.0
        }

def get_ai_entry_signal(
    symbol: str,
    exchange: str,
    technical_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Get AI opinion on entry signal.
    
    Args:
        symbol: Trading symbol
        exchange: Exchange name
        technical_data: Dict with technical indicators (RSI, MACD, ADX, etc.)
        
    Returns:
        Dict with AI entry recommendation including confidence level
    """
    if not CLAWDBOT_ENABLED or get_bridge_service is None:
        return {
            "enabled": False,
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": "Clawdbot disabled"
        }
    
    try:
        # Get market context first
        market_context = get_ai_market_context(symbol, exchange)
        
        # Combine with technical data for AI analysis
        bridge = get_bridge_service()
        
        # Create prompt for entry analysis
        prompt_data = {
            "symbol": symbol,
            "exchange": exchange,
            "technical_indicators": technical_data,
            "market_context": market_context
        }
        
        # Use bridge to get entry recommendation
        # For now, use market context to infer entry signal
        regime = market_context.get("regime", "UNKNOWN")
        sentiment = market_context.get("sentiment", "NEUTRAL")
        confidence = market_context.get("confidence", 0.0)
        
        # Simple logic: if bullish sentiment and trending regime, recommend entry
        if sentiment == "BULLISH" and regime in ["TRENDING", "MIXED"] and confidence > 0.6:
            recommendation = "BUY"
        elif sentiment == "BEARISH" and regime in ["TRENDING", "MIXED"] and confidence > 0.6:
            recommendation = "SELL"
        else:
            recommendation = "NEUTRAL"
        
        return {
            "enabled": True,
            "recommendation": recommendation,
            "confidence": confidence,
            "regime": regime,
            "sentiment": sentiment,
            "reasoning": f"Market regime: {regime}, Sentiment: {sentiment}, Confidence: {confidence:.2f}"
        }
    except Exception as e:
        logger.error(f"Error in get_ai_entry_signal: {e}")
        return {
            "enabled": True,
            "error": str(e),
            "recommendation": "NEUTRAL",
            "confidence": 0.0
        }

def get_ai_exit_signal(position: Dict[str, Any], current_price: float) -> Dict[str, Any]:
    """
    Get AI opinion on exit signal.
    
    Args:
        position: Dict with position details (symbol, entry_price, quantity, side)
        current_price: Current market price
        
    Returns:
        Dict with AI exit recommendation
    """
    if not CLAWDBOT_ENABLED or get_bridge_service is None:
        return {
            "enabled": False,
            "recommendation": "HOLD",
            "confidence": 0.0
        }
    
    try:
        symbol = position.get("symbol", "")
        exchange = position.get("exchange", "NSE")
        entry_price = position.get("entry_price", 0)
        side = position.get("side", "LONG")
        
        # Calculate P&L
        if side == "LONG":
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        # Get current market context
        market_context = get_ai_market_context(symbol, exchange)
        
        # Simple exit logic based on P&L and market context
        sentiment = market_context.get("sentiment", "NEUTRAL")
        confidence = market_context.get("confidence", 0.0)
        
        # If profit and sentiment changed against position, consider exit
        if pnl_pct > 2.0:  # 2% profit
            if (side == "LONG" and sentiment == "BEARISH") or (side == "SHORT" and sentiment == "BULLISH"):
                recommendation = "EXIT"
                confidence = min(confidence + 0.2, 1.0)
            else:
                recommendation = "HOLD"
        elif pnl_pct < -1.5:  # 1.5% loss
            recommendation = "EXIT"
            confidence = 0.8
        else:
            recommendation = "HOLD"
        
        return {
            "enabled": True,
            "recommendation": recommendation,
            "confidence": confidence,
            "pnl_pct": pnl_pct,
            "reasoning": f"P&L: {pnl_pct:.2f}%, Market sentiment: {sentiment}"
        }
    except Exception as e:
        logger.error(f"Error in get_ai_exit_signal: {e}")
        return {
            "enabled": True,
            "error": str(e),
            "recommendation": "HOLD",
            "confidence": 0.0
        }

def get_ai_position_size(
    symbol: str,
    signal_strength: float,
    account_balance: float,
    base_risk_pct: float = 1.0
) -> Dict[str, Any]:
    """
    Get AI-suggested position size multiplier.
    
    Args:
        symbol: Trading symbol
        signal_strength: Technical signal strength (0-100)
        account_balance: Account balance
        base_risk_pct: Base risk percentage
        
    Returns:
        Dict with position size multiplier and reasoning
    """
    if not CLAWDBOT_ENABLED or get_bridge_service is None:
        return {
            "enabled": False,
            "multiplier": 1.0,
            "reasoning": "Clawdbot disabled"
        }
    
    try:
        market_context = get_ai_market_context(symbol)
        confidence = market_context.get("confidence", 0.5)
        regime = market_context.get("regime", "UNKNOWN")
        
        # Calculate multiplier based on AI confidence and signal strength
        # High confidence + high signal strength = larger position
        # Low confidence or ranging market = smaller position
        
        if regime == "TRENDING" and confidence > 0.7 and signal_strength > 75:
            multiplier = 1.2  # Increase position size
        elif regime == "RANGING" or confidence < 0.4:
            multiplier = 0.7  # Reduce position size
        elif signal_strength > 75 and confidence > 0.6:
            multiplier = 1.0  # Normal size
        else:
            multiplier = 0.8  # Slightly reduced
        
        return {
            "enabled": True,
            "multiplier": multiplier,
            "confidence": confidence,
            "regime": regime,
            "reasoning": f"Regime: {regime}, AI confidence: {confidence:.2f}, Signal strength: {signal_strength}"
        }
    except Exception as e:
        logger.error(f"Error in get_ai_position_size: {e}")
        return {
            "enabled": True,
            "error": str(e),
            "multiplier": 1.0
        }

def get_ai_parameter_suggestion(
    strategy_name: str,
    indicator_values: Dict[str, float]
) -> Dict[str, Any]:
    """
    Get AI-suggested parameter adjustments.
    
    Args:
        strategy_name: Name of the strategy
        indicator_values: Current indicator values
        
    Returns:
        Dict with parameter suggestions
    """
    if not CLAWDBOT_ENABLED or get_bridge_service is None:
        return {
            "enabled": False,
            "suggestions": {},
            "reasoning": "Clawdbot disabled"
        }
    
    try:
        bridge = get_bridge_service()
        result = _run_async(bridge.get_strategy_recommendation(
            strategy_name,
            indicator_values
        ))
        
        if "error" in result:
            return {
                "enabled": True,
                "error": result["error"],
                "suggestions": {}
            }
        
        recommendations = result.get("recommendations", {})
        return {
            "enabled": True,
            "suggestions": recommendations.get("parameter_changes", {}),
            "expected_impact": recommendations.get("expected_impact", ""),
            "confidence": recommendations.get("confidence", 0.5),
            "full_recommendation": result
        }
    except Exception as e:
        logger.error(f"Error in get_ai_parameter_suggestion: {e}")
        return {
            "enabled": True,
            "error": str(e),
            "suggestions": {}
        }

def send_ai_alert(message: str, priority: str = "info", channel: str = "telegram") -> bool:
    """
    Send alert through Clawdbot channels.
    
    Args:
        message: Alert message
        priority: Priority level (info, warning, critical)
        channel: Channel name (telegram, whatsapp, slack)
        
    Returns:
        bool: True if sent successfully
    """
    if not CLAWDBOT_ENABLED or get_bridge_service is None:
        logger.debug("Clawdbot disabled, alert not sent")
        return False
    
    try:
        bridge = get_bridge_service()
        result = _run_async(bridge.send_trading_alert(channel, message, priority))
        return result.get("status") == "sent"
    except Exception as e:
        logger.error(f"Error sending alert: {e}")
        return False
