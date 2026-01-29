"""
Strategy Parameter Injector
---------------------------
Dynamically injects parameters into strategy modules for backtesting optimization.
"""
import os
import sys
import importlib
import importlib.util
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger("ParamInjector")

def load_strategy_module(strategy_name: str):
    """
    Load a strategy module dynamically.
    
    Args:
        strategy_name: Name of strategy (e.g., 'natural_gas_clawdbot', 'crude_oil_enhanced')
    
    Returns:
        Strategy module object
    """
    script_dir = Path(__file__).parent.parent / 'scripts'
    
    # Map strategy names to file names
    strategy_files = {
        'natural_gas_clawdbot': 'natural_gas_clawdbot_strategy.py',
        'crude_oil_enhanced': 'crude_oil_enhanced_strategy.py',
        'crude_oil_clawdbot': 'crude_oil_clawdbot_strategy.py',
        'mcx_clawdbot': 'mcx_clawdbot_strategy.py'
    }
    
    filename = strategy_files.get(strategy_name)
    if not filename:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    
    filepath = script_dir / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Strategy file not found: {filepath}")
    
    # Load module
    spec = importlib.util.spec_from_file_location(f"strategy_{strategy_name}", filepath)
    module = importlib.util.module_from_spec(spec)
    
    # Add to sys.modules to allow imports within the module
    sys.modules[f"strategy_{strategy_name}"] = module
    
    spec.loader.exec_module(module)
    
    return module

def inject_parameters(module, parameters: Dict[str, Any]):
    """
    Inject parameters into a strategy module.
    
    Args:
        module: Strategy module object
        parameters: Dictionary of parameter name -> value mappings
    
    Returns:
        Modified module
    """
    # Inject simple parameters (constants)
    for param_name, param_value in parameters.items():
        if param_name.startswith('TIMEFRAME_') or param_name.startswith('TRENDING_') or param_name.startswith('RANGING_'):
            # Handle special cases for dictionaries
            continue
        setattr(module, param_name, param_value)
    
    # Handle TIMEFRAME_WEIGHTS
    if 'TIMEFRAME_WEIGHTS' in parameters:
        module.TIMEFRAME_WEIGHTS = parameters['TIMEFRAME_WEIGHTS'].copy()
    
    # Handle TRENDING_WEIGHTS
    if 'TRENDING_WEIGHTS' in parameters:
        module.TRENDING_WEIGHTS = parameters['TRENDING_WEIGHTS'].copy()
    
    # Handle RANGING_WEIGHTS
    if 'RANGING_WEIGHTS' in parameters:
        module.RANGING_WEIGHTS = parameters['RANGING_WEIGHTS'].copy()
    
    return module

def prepare_parameters_for_injection(params: Dict[str, Any], strategy_name: str) -> Dict[str, Any]:
    """
    Prepare parameters dictionary for injection into strategy module.
    Handles normalization of weights and timeframe weights.
    
    Args:
        params: Raw parameters dictionary
        strategy_name: Strategy name
    
    Returns:
        Prepared parameters dictionary
    """
    try:
        from parameter_space import normalize_weights, normalize_timeframe_weights
    except ImportError:
        # Fallback normalization functions
        def normalize_weights(weights):
            total = sum(weights.values())
            return {k: v / total for k, v in weights.items()} if total > 0 else weights
        normalize_timeframe_weights = normalize_weights
    
    prepared = params.copy()
    
    # Normalize timeframe weights if provided
    if 'TIMEFRAME_15m' in params or 'TIMEFRAME_5m' in params or 'TIMEFRAME_1h' in params:
        tf_weights = {}
        if 'TIMEFRAME_15m' in params:
            tf_weights['15m'] = params['TIMEFRAME_15m']
        if 'TIMEFRAME_5m' in params:
            tf_weights['5m'] = params['TIMEFRAME_5m']
        if 'TIMEFRAME_1h' in params:
            tf_weights['1h'] = params['TIMEFRAME_1h']
        
        # Ensure they sum to 1.0
        total = sum(tf_weights.values())
        if total > 0:
            tf_weights = {k: v / total for k, v in tf_weights.items()}
        else:
            # Default weights
            tf_weights = {'5m': 0.25, '15m': 0.50, '1h': 0.25}
        
        prepared['TIMEFRAME_WEIGHTS'] = tf_weights
        
        # Remove individual timeframe params
        for key in list(prepared.keys()):
            if key.startswith('TIMEFRAME_'):
                del prepared[key]
    
    # Normalize trending weights if provided
    if any(k.startswith('TRENDING_') for k in params.keys()):
        trending = {}
        for key, value in params.items():
            if key.startswith('TRENDING_'):
                indicator = key.replace('TRENDING_', '')
                trending[indicator] = value
        
        if trending:
            # Get default structure from module to fill missing keys
            try:
                module = load_strategy_module(strategy_name)
                default_trending = getattr(module, 'TRENDING_WEIGHTS', {})
                for key in default_trending:
                    if key not in trending:
                        trending[key] = default_trending[key]
            except:
                pass
            
            prepared['TRENDING_WEIGHTS'] = normalize_weights(trending)
            
            # Remove individual trending params
            for key in list(prepared.keys()):
                if key.startswith('TRENDING_'):
                    del prepared[key]
    
    # Normalize ranging weights if provided
    if any(k.startswith('RANGING_') for k in params.keys()):
        ranging = {}
        for key, value in params.items():
            if key.startswith('RANGING_'):
                indicator = key.replace('RANGING_', '')
                ranging[indicator] = value
        
        if ranging:
            # Get default structure from module
            try:
                module = load_strategy_module(strategy_name)
                default_ranging = getattr(module, 'RANGING_WEIGHTS', {})
                for key in default_ranging:
                    if key not in ranging:
                        ranging[key] = default_ranging[key]
            except:
                pass
            
            prepared['RANGING_WEIGHTS'] = normalize_weights(ranging)
            
            # Remove individual ranging params
            for key in list(prepared.keys()):
                if key.startswith('RANGING_'):
                    del prepared[key]
    
    return prepared

def create_strategy_with_params(strategy_name: str, parameters: Dict[str, Any]):
    """
    Create a strategy module instance with injected parameters.
    
    Args:
        strategy_name: Strategy name
        parameters: Parameters to inject
    
    Returns:
        Strategy module with parameters injected
    """
    # Load fresh module
    module = load_strategy_module(strategy_name)
    
    # Prepare parameters
    prepared_params = prepare_parameters_for_injection(parameters, strategy_name)
    
    # Inject parameters
    module = inject_parameters(module, prepared_params)
    
    return module

def get_strategy_symbol(strategy_name: str) -> str:
    """Get the default symbol for a strategy"""
    symbol_map = {
        'natural_gas_clawdbot': 'NATURALGAS24FEB26FUT',
        'crude_oil_enhanced': 'CRUDEOIL19FEB26FUT',
        'crude_oil_clawdbot': 'CRUDEOIL19FEB26FUT',
        'mcx_clawdbot': 'GOLDM05FEB26FUT'
    }
    return symbol_map.get(strategy_name, 'UNKNOWN')
