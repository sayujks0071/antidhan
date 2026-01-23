"""Adapter for nifty_multistrike_momentum_20260122.py strategy"""
# This adapter is very similar to Greeks Enhanced, so we'll reuse most logic
# For now, create a simplified version that inherits from Greeks Enhanced adapter

import os
import sys

# Add paths
_script_dir = os.path.dirname(os.path.abspath(__file__))
_strategies_dir = os.path.dirname(_script_dir)
_utils_dir = os.path.join(_strategies_dir, 'utils')
_scripts_dir = os.path.join(_strategies_dir, 'scripts')

sys.path.insert(0, _strategies_dir)
sys.path.insert(0, _utils_dir)
sys.path.insert(0, _scripts_dir)

from nifty_greeks_enhanced_adapter import NiftyGreeksEnhancedAdapter

class NiftyMultistrikeMomentumAdapter(NiftyGreeksEnhancedAdapter):
    """Adapter for NIFTY Multi-Strike Momentum strategy"""
    
    def __init__(self, name: str = "NIFTY Multi-Strike Momentum", params: dict = None):
        # Import multistrike constants
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
        
        from nifty_multistrike_momentum_20260122 import (
            UNDERLYING, UNDERLYING_EXCHANGE, OPTIONS_EXCHANGE,
            ACCOUNT_SIZE, RISK_PCT, MAX_POSITIONS,
            EMA_FAST, EMA_SLOW, ADX_PERIOD, ATR_PERIOD, RSI_PERIOD,
            MIN_ADX, MIN_ATR_PCT,
            RSI_LONG_MIN, RSI_LONG_MAX, RSI_SHORT_MIN, RSI_SHORT_MAX,
            VWAP_MIN_DIST, SL_PCT, TP1_PCT, TP2_PCT,
            SKIP_FIRST_MINUTES, SKIP_LAST_MINUTES,
            HIGH_MOMENTUM_SCORE, NORMAL_MOMENTUM_SCORE
        )
        
        # Store constants as instance variables for use in methods
        self.UNDERLYING = UNDERLYING
        self.UNDERLYING_EXCHANGE = UNDERLYING_EXCHANGE
        self.OPTIONS_EXCHANGE = OPTIONS_EXCHANGE
        self.ACCOUNT_SIZE = ACCOUNT_SIZE
        self.RISK_PCT = RISK_PCT
        self.MAX_POSITIONS = MAX_POSITIONS
        self.EMA_FAST = EMA_FAST
        self.EMA_SLOW = EMA_SLOW
        self.ADX_PERIOD = ADX_PERIOD
        self.ATR_PERIOD = ATR_PERIOD
        self.RSI_PERIOD = RSI_PERIOD
        self.MIN_ADX = MIN_ADX
        self.MIN_ATR_PCT = MIN_ATR_PCT
        self.RSI_LONG_MIN = RSI_LONG_MIN
        self.RSI_LONG_MAX = RSI_LONG_MAX
        self.RSI_SHORT_MIN = RSI_SHORT_MIN
        self.RSI_SHORT_MAX = RSI_SHORT_MAX
        self.VWAP_MIN_DIST = VWAP_MIN_DIST
        self.SL_PCT = SL_PCT
        self.TP1_PCT = TP1_PCT
        self.TP2_PCT = TP2_PCT
        self.SKIP_FIRST_MINUTES = SKIP_FIRST_MINUTES
        self.SKIP_LAST_MINUTES = SKIP_LAST_MINUTES
        self.HIGH_MOMENTUM_SCORE = HIGH_MOMENTUM_SCORE
        self.NORMAL_MOMENTUM_SCORE = NORMAL_MOMENTUM_SCORE
        
        strategy_path = os.path.join(
            _scripts_dir,
            'nifty_multistrike_momentum_20260122.py'
        )
        # Call StrategyAdapter.__init__ directly
        from strategy_adapter import StrategyAdapter
        StrategyAdapter.__init__(self, name, params or {}, strategy_path)
        
        # Initialize heat tracker
        from aitrapp_utils import PortfolioHeatTracker
        self.heat_tracker = PortfolioHeatTracker(ACCOUNT_SIZE, max_heat_pct=2.0)
        self.daily_pnl = 0.0
    
    def _extract_signals(self, context):
        """Override to use multistrike logic"""
        # For now, use parent logic but adjust delta selection for multistrike
        signals = super()._extract_signals(context)
        
        # Multistrike strategy can select multiple strikes, but for backtesting
        # we'll keep it simple and just use one strike per signal
        return signals
