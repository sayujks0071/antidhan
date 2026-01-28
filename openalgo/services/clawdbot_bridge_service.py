#!/usr/bin/env python3
"""
Clawdbot Bridge Service
Connects OpenAlgo to Clawdbot Gateway for AI-powered trading enhancements.
"""
import os
import json
import logging
import time
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import httpx
import websockets
from functools import lru_cache
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ClawdbotBridge")

class ClawdbotBridgeService:
    """
    Bridge service connecting OpenAlgo to Clawdbot Gateway.
    Provides AI-powered market analysis, strategy recommendations, and alert routing.
    """
    
    def __init__(
        self,
        gateway_url: str = "ws://127.0.0.1:18789",
        http_url: str = "http://127.0.0.1:18789",
        cache_ttl: int = 60
    ):
        self.gateway_url = gateway_url
        self.http_url = http_url
        self.cache_ttl = cache_ttl
        self.cache: Dict[str, tuple] = {}  # {key: (data, timestamp)}
        self.cache_lock = Lock()
        self.ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self.enabled = os.getenv("CLAWDBOT_ENABLED", "true").lower() == "true"
        
        if not self.enabled:
            logger.warning("Clawdbot bridge is disabled via CLAWDBOT_ENABLED=false")
    
    def _get_cache_key(self, method: str, **kwargs) -> str:
        """Generate cache key from method and parameters"""
        return f"{method}:{json.dumps(kwargs, sort_keys=True)}"
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        with self.cache_lock:
            if key in self.cache:
                data, timestamp = self.cache[key]
                if time.time() - timestamp < self.cache_ttl:
                    return data
                else:
                    del self.cache[key]
            return None
    
    def _set_cache(self, key: str, value: Any):
        """Store value in cache"""
        with self.cache_lock:
            self.cache[key] = (value, time.time())
    
    async def _send_ws_message(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send message via WebSocket to Clawdbot Gateway"""
        # Debug logging
        debug_log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
        try:
            log_entry = {
                "sessionId": "clawdbot-bridge-debug",
                "runId": "run1",
                "hypothesisId": "H7",
                "location": "clawdbot_bridge_service.py:64",
                "message": "_send_ws_message called",
                "data": {"method": method, "enabled": self.enabled, "gateway_url": self.gateway_url},
                "timestamp": int(time.time() * 1000)
            }
            with open(debug_log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception:
            pass
        
        if not self.enabled:
            return {"error": "Clawdbot bridge is disabled"}
        
        try:
            # Check if connection exists and is open
            need_new_connection = True
            if self.ws_connection is not None:
                try:
                    # Check connection state - websockets uses 'close_code' or 'state' to check if closed
                    # If connection is closed, accessing state will raise or return None
                    if hasattr(self.ws_connection, 'closed'):
                        need_new_connection = self.ws_connection.closed
                    elif hasattr(self.ws_connection, 'close_code'):
                        # If close_code is not None, connection is closed
                        need_new_connection = (self.ws_connection.close_code is not None)
                    else:
                        # If we can't determine, try to reconnect
                        need_new_connection = True
                except (AttributeError, Exception):
                    # If any error checking connection state, assume it's closed
                    need_new_connection = True
            
            if self.ws_connection is None or need_new_connection:
                try:
                    log_entry = {
                        "sessionId": "clawdbot-bridge-debug",
                        "runId": "run1",
                        "hypothesisId": "H7",
                        "location": "clawdbot_bridge_service.py:71",
                        "message": "Attempting WebSocket connection",
                        "data": {"gateway_url": self.gateway_url},
                        "timestamp": int(time.time() * 1000)
                    }
                    with open(debug_log_path, 'a') as f:
                        f.write(json.dumps(log_entry) + '\n')
                except Exception:
                    pass
                self.ws_connection = await asyncio.wait_for(
                    websockets.connect(self.gateway_url),
                    timeout=5.0
                )
                
                # Handle authentication challenge according to Clawdbot protocol
                try:
                    # Wait for initial challenge message
                    initial_msg = await asyncio.wait_for(self.ws_connection.recv(), timeout=2.0)
                    initial_data = json.loads(initial_msg)
                    
                    if initial_data.get("event") == "connect.challenge":
                        challenge_nonce = initial_data.get("payload", {}).get("nonce")
                        logger.info(f"Clawdbot gateway challenge received (nonce: {challenge_nonce[:8] if challenge_nonce else 'none'}...)")
                        
                        # Send connect request (for local gateway, minimal auth required)
                        connect_id = str(int(time.time() * 1000))
                        connect_request = {
                            "type": "req",
                            "id": connect_id,
                            "method": "connect",
                            "params": {
                                "minProtocol": 3,
                                "maxProtocol": 3,
                                "client": {
                                    "id": "openalgo-bridge",
                                    "version": "1.0.0",
                                    "platform": "python",
                                    "mode": "operator"
                                },
                                "role": "operator",
                                "scopes": ["operator.read", "operator.write"],
                                "auth": {
                                    "token": os.getenv("CLAWDBOT_GATEWAY_TOKEN", "")
                                },
                                "locale": "en-US",
                                "userAgent": "openalgo-bridge/1.0.0",
                                "device": {
                                    "id": "openalgo-bridge-device",
                                    "publicKey": "",
                                    "signature": "",
                                    "signedAt": int(time.time() * 1000),
                                    "nonce": challenge_nonce or ""
                                }
                            }
                        }
                        
                        await self.ws_connection.send(json.dumps(connect_request))
                        
                        # Wait for hello-ok response
                        hello_response = await asyncio.wait_for(self.ws_connection.recv(), timeout=5.0)
                        hello_data = json.loads(hello_response)
                        
                        if hello_data.get("type") == "res" and hello_data.get("ok"):
                            logger.info("Clawdbot gateway authenticated successfully")
                        else:
                            logger.warning(f"Unexpected connect response: {hello_data}")
                            
                except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
                    # For local gateway, continue anyway
                    logger.debug(f"Challenge handling: {e} (continuing for local gateway)")
            
            # Send the actual method request
            message_id = str(int(time.time() * 1000))
            message = {
                "type": "req",
                "id": message_id,
                "method": method,
                "params": params or {}
            }
            
            await self.ws_connection.send(json.dumps(message))
            
            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(self.ws_connection.recv(), timeout=30.0)
                response_data = json.loads(response)
                
                # Handle response format
                if response_data.get("type") == "res":
                    if response_data.get("ok"):
                        return response_data.get("payload", {})
                    else:
                        return {"error": response_data.get("error", "Unknown error")}
                elif response_data.get("type") == "event":
                    # Event response
                    return response_data
                else:
                    return response_data
                    
            except asyncio.TimeoutError:
                return {"error": "Timeout waiting for response from Clawdbot gateway"}
        except Exception as e:
            try:
                log_entry = {
                    "sessionId": "clawdbot-bridge-debug",
                    "runId": "run1",
                    "hypothesisId": "H7",
                    "location": "clawdbot_bridge_service.py:84",
                    "message": "WebSocket error occurred",
                    "data": {"error": str(e), "error_type": type(e).__name__},
                    "timestamp": int(time.time() * 1000)
                }
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps(log_entry) + '\n')
            except Exception:
                pass
            logger.error(f"WebSocket error: {e}")
            return {"error": str(e)}
    
    async def _send_http_request(self, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send HTTP request to Clawdbot Gateway"""
        if not self.enabled:
            return {"error": "Clawdbot bridge is disabled"}
        
        try:
            url = f"{self.http_url}{endpoint}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=data or {})
                return response.json()
        except Exception as e:
            logger.error(f"HTTP request error: {e}")
            return {"error": str(e)}
    
    async def get_market_analysis(
        self,
        symbol: str,
        exchange: str = "NSE",
        timeframe: str = "5m"
    ) -> Dict[str, Any]:
        """
        Get AI-powered market analysis for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange name
            timeframe: Timeframe for analysis
            
        Returns:
            Dict with market analysis including regime, sentiment, recommendations
        """
        cache_key = self._get_cache_key("market_analysis", symbol=symbol, exchange=exchange, timeframe=timeframe)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        try:
            # Use Clawdbot agent to analyze market
            prompt = f"""
            Analyze the market conditions for {symbol} on {exchange} using {timeframe} timeframe.
            Provide:
            1. Market Regime (TRENDING/RANGING/MIXED)
            2. Trend Strength (0-100)
            3. Volatility Level (LOW/MEDIUM/HIGH)
            4. Key Support/Resistance Levels
            5. Trading Recommendation (BULLISH/NEUTRAL/BEARISH)
            6. Confidence Level (0-100%)
            
            Format as JSON.
            """
            
            result = await self._send_ws_message("agent.send", {
                "message": prompt,
                "session": "trading-analysis"
            })
            
            analysis = {
                "symbol": symbol,
                "exchange": exchange,
                "timeframe": timeframe,
                "timestamp": datetime.now().isoformat(),
                "analysis": result.get("response", {}),
                "source": "clawdbot"
            }
            
            self._set_cache(cache_key, analysis)
            return analysis
        except Exception as e:
            logger.error(f"Error getting market analysis: {e}")
            return {"error": str(e)}
    
    async def get_strategy_recommendation(
        self,
        strategy_name: str,
        current_params: Dict[str, Any],
        market_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Get AI recommendations for strategy parameter adjustments.
        
        Args:
            strategy_name: Name of the strategy
            current_params: Current strategy parameters
            market_data: Optional market data for context
            
        Returns:
            Dict with recommended parameter changes
        """
        cache_key = self._get_cache_key("strategy_recommendation", 
                                       strategy=strategy_name, 
                                       params=current_params)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        try:
            prompt = f"""
            Analyze the strategy '{strategy_name}' with current parameters:
            {json.dumps(current_params, indent=2)}
            
            Market data context:
            {json.dumps(market_data or {}, indent=2)}
            
            Suggest parameter optimizations:
            1. Recommended parameter changes
            2. Expected impact
            3. Risk assessment
            4. Confidence level
            
            Format as JSON.
            """
            
            result = await self._send_ws_message("agent.send", {
                "message": prompt,
                "session": "strategy-optimization"
            })
            
            recommendation = {
                "strategy": strategy_name,
                "current_params": current_params,
                "recommendations": result.get("response", {}),
                "timestamp": datetime.now().isoformat(),
                "source": "clawdbot"
            }
            
            self._set_cache(cache_key, recommendation)
            return recommendation
        except Exception as e:
            logger.error(f"Error getting strategy recommendation: {e}")
            return {"error": str(e)}
    
    async def send_trading_alert(
        self,
        channel: str,
        message: str,
        priority: str = "info"
    ) -> Dict[str, Any]:
        """
        Send trading alert via Clawdbot channels.
        
        Args:
            channel: Channel name (telegram, whatsapp, slack, etc.)
            message: Alert message
            priority: Priority level (info, warning, critical)
            
        Returns:
            Dict with send status
        """
        if not self.enabled:
            logger.warning("Clawdbot bridge disabled, alert not sent")
            return {"status": "disabled"}
        
        try:
            # Format message with priority indicator
            emoji_map = {
                "info": "ℹ️",
                "warning": "⚠️",
                "critical": "🚨"
            }
            formatted_message = f"{emoji_map.get(priority, 'ℹ️')} {message}"
            
            # Send via Clawdbot message API
            result = await self._send_http_request("/message/send", {
                "channel": channel,
                "message": formatted_message,
                "priority": priority
            })
            
            return {
                "status": "sent",
                "channel": channel,
                "message": formatted_message,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
            return {"error": str(e)}
    
    async def get_risk_assessment(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get AI-powered risk assessment for current positions.
        
        Args:
            positions: List of position dictionaries
            
        Returns:
            Dict with risk assessment and recommendations
        """
        cache_key = self._get_cache_key("risk_assessment", positions=positions)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        try:
            prompt = f"""
            Assess the risk of the following positions:
            {json.dumps(positions, indent=2)}
            
            Provide:
            1. Portfolio Risk Level (LOW/MEDIUM/HIGH)
            2. Total Exposure (percentage of capital)
            3. Concentration Risk analysis
            4. Correlation Risk assessment
            5. Risk management recommendations
            6. Urgency level
            
            Format as JSON.
            """
            
            result = await self._send_ws_message("agent.send", {
                "message": prompt,
                "session": "risk-assessment"
            })
            
            assessment = {
                "positions": positions,
                "assessment": result.get("response", {}),
                "timestamp": datetime.now().isoformat(),
                "source": "clawdbot"
            }
            
            self._set_cache(cache_key, assessment)
            return assessment
        except Exception as e:
            logger.error(f"Error getting risk assessment: {e}")
            return {"error": str(e)}
    
    async def optimize_strategy_parameters(
        self,
        strategy_name: str,
        performance_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get AI suggestions for strategy parameter optimization.
        
        Args:
            strategy_name: Name of the strategy
            performance_data: Performance metrics and trade history
            
        Returns:
            Dict with optimization suggestions
        """
        cache_key = self._get_cache_key("optimize_params", 
                                       strategy=strategy_name, 
                                       performance=performance_data)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        try:
            prompt = f"""
            Analyze performance data for strategy '{strategy_name}':
            {json.dumps(performance_data, indent=2)}
            
            Suggest parameter optimizations:
            1. Parameter changes to improve performance
            2. Expected impact on win rate and returns
            3. Risk considerations
            4. Confidence level
            
            Format as JSON.
            """
            
            result = await self._send_ws_message("agent.send", {
                "message": prompt,
                "session": "parameter-optimization"
            })
            
            optimization = {
                "strategy": strategy_name,
                "performance_data": performance_data,
                "suggestions": result.get("response", {}),
                "timestamp": datetime.now().isoformat(),
                "source": "clawdbot"
            }
            
            self._set_cache(cache_key, optimization)
            return optimization
        except Exception as e:
            logger.error(f"Error optimizing parameters: {e}")
            return {"error": str(e)}
    
    async def close(self):
        """Close WebSocket connection"""
        if self.ws_connection and not self.ws_connection.closed:
            await self.ws_connection.close()


# Singleton instance
_bridge_instance: Optional[ClawdbotBridgeService] = None

def get_bridge_service() -> ClawdbotBridgeService:
    """Get or create singleton bridge service instance"""
    global _bridge_instance
    if _bridge_instance is None:
        gateway_url = os.getenv("CLAWDBOT_GATEWAY_URL", "ws://127.0.0.1:18789")
        http_url = gateway_url.replace("ws://", "http://").replace("wss://", "https://")
        _bridge_instance = ClawdbotBridgeService(gateway_url=gateway_url, http_url=http_url)
    return _bridge_instance
