"""Base strategy adapter for OpenAlgo strategies to work with AITRAPP backtest engine"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional
import sys
import os

# Handle both relative and absolute imports
try:
    from .aitrapp_integration import Strategy, StrategyContext, Signal, SignalSide, Instrument, InstrumentType
    from .openalgo_mock import set_current_timestamp, get_mock
except ImportError:
    # Absolute import fallback
    _utils_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _utils_dir)
    from aitrapp_integration import Strategy, StrategyContext, Signal, SignalSide, Instrument, InstrumentType
    from openalgo_mock import set_current_timestamp, get_mock


class StrategyAdapter(Strategy):
    """Base adapter class for OpenAlgo strategies"""
    
    def __init__(self, name: str, params: Dict[str, Any], strategy_module_path: str):
        """
        Initialize adapter
        
        Args:
            name: Strategy name
            params: Strategy parameters
            strategy_module_path: Path to original strategy Python file
        """
        super().__init__(name, params)
        self.strategy_module_path = strategy_module_path
        self.strategy_module = None
        self._load_strategy_module()
        
        # Strategy state (reset for each backtest)
        self._reset_state()
    
    def _load_strategy_module(self):
        """Load the original strategy module"""
        import importlib.util
        
        spec = importlib.util.spec_from_file_location(
            "strategy_module",
            self.strategy_module_path
        )
        self.strategy_module = importlib.util.module_from_spec(spec)
        
        # We'll execute it later with mocked API
        self._strategy_globals = {}
    
    def _reset_state(self):
        """Reset strategy state for new backtest"""
        # This will be overridden by subclasses
        pass
    
    def generate_signals(self, context: StrategyContext) -> List[Signal]:
        """
        Generate trading signals from the adapted strategy
        
        Args:
            context: AITRAPP strategy context
            
        Returns:
            List of signals
        """
        # Set current timestamp for API mock
        set_current_timestamp(context.timestamp)
        
        # Reset state if needed
        self._reset_state()
        
        # Extract entry logic from strategy
        signals = self._extract_signals(context)
        
        return signals
    
    @abstractmethod
    def _extract_signals(self, context: StrategyContext) -> List[Signal]:
        """
        Extract signals from the original strategy
        
        This method should be implemented by subclasses to:
        1. Mock the API calls using get_mock()
        2. Call the original strategy's entry logic
        3. Convert strategy's entry conditions to AITRAPP Signal objects
        
        Args:
            context: Strategy context
            
        Returns:
            List of signals
        """
        pass
    
    def _create_signal(
        self,
        instrument: Instrument,
        side: SignalSide,
        entry_price: float,
        stop_loss: float,
        take_profit_1: Optional[float] = None,
        take_profit_2: Optional[float] = None,
        confidence: float = 0.5,
        rationale: str = ""
    ) -> Signal:
        """Create a Signal object"""
        return Signal(
            strategy_name=self.name,
            timestamp=datetime.now(),
            instrument=instrument,
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            confidence=confidence,
            rationale=rationale,
            risk_amount=abs(entry_price - stop_loss),
            reward_amount=abs(take_profit_1 - entry_price) if take_profit_1 else 0.0
        )
    
    def _mock_api_in_strategy(self):
        """Replace API calls in strategy module with mocked versions"""
        mock = get_mock()
        if not mock:
            return
        
        # Monkey-patch the post_json function in strategy module
        if hasattr(self.strategy_module, 'post_json'):
            original_post_json = self.strategy_module.post_json
            
            def mocked_post_json(path, payload, timeout=15):
                return mock.post_json(path, payload)
            
            self.strategy_module.post_json = mocked_post_json
