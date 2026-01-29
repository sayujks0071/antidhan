"""
Parameter Space Definitions for Strategy Optimization
------------------------------------------------------
Defines parameter ranges and constraints for optimizing MCX strategies.
"""
from typing import Dict, List, Tuple, Any
import numpy as np

# Parameter space definitions for each strategy
PARAMETER_SPACES = {
    'natural_gas_clawdbot': {
        'indicator_periods': {
            'RSI_PERIOD': [10, 12, 14, 16, 18],
            'MACD_FAST': [10, 12, 14],
            'MACD_SLOW': [24, 26, 28],
            'MACD_SIGNAL': [7, 9, 11],
            'ADX_PERIOD': [12, 14, 16],
            'ATR_PERIOD': [12, 14, 16],
            'BB_PERIOD': [18, 20, 22],
            'BB_STD': [1.8, 2.0, 2.2],
            'EMA_FAST': [7, 9, 11],
            'EMA_SLOW': [19, 21, 23],
            'EMA_LONG': [45, 50, 55],
            'VWAP_PERIOD': [18, 20, 22]
        },
        'entry_thresholds': {
            'BASE_ENTRY_THRESHOLD': [50, 55, 60, 65, 70],
            'MIN_ENTRY_THRESHOLD': [45, 50, 55],
            'MAX_ENTRY_THRESHOLD': [70, 75, 80],
            'ADX_ADAPTIVE_FACTOR': [0.3, 0.4, 0.5],
            'AI_CONFIDENCE_MULTIPLIER': [0.15, 0.20, 0.25]
        },
        'risk_management': {
            'ATR_SL_MULTIPLIER': [2.0, 2.5, 3.0],
            'ATR_TP_MULTIPLIER': [3.5, 4.0, 4.5, 5.0],
            'TRAILING_STOP_ATR': [1.0, 1.5, 2.0],
            'BREAKEVEN_ATR': [1.0, 1.5, 2.0]
        },
        'timeframe_weights': {
            '5m': [0.20, 0.25, 0.30, 0.35],
            '15m': [0.40, 0.50, 0.60, 0.70],
            '1h': [0.10, 0.15, 0.20, 0.25]
        },
        'trending_weights': {
            'MACD': [0.20, 0.25, 0.30],
            'ADX': [0.20, 0.25, 0.30],
            'RSI': [0.10, 0.15, 0.20],
            'BOLLINGER': [0.10, 0.15, 0.20],
            'EMA_CROSS': [0.08, 0.10, 0.12],
            'VOLUME': [0.08, 0.10, 0.12],
            'VWAP': [0.00, 0.05]
        },
        'ranging_weights': {
            'RSI': [0.25, 0.30, 0.35],
            'BOLLINGER': [0.25, 0.30, 0.35],
            'VOLUME': [0.15, 0.20, 0.25],
            'VWAP': [0.08, 0.10, 0.12],
            'EMA_CROSS': [0.03, 0.05, 0.07],
            'MACD': [0.03, 0.05, 0.07]
        },
        'position_sizing': {
            'BASE_QUANTITY': [1],
            'MAX_POSITION_SIZE': [2],
            'RISK_PER_TRADE_PCT': [1.0, 1.5, 2.0]
        }
    },
    'crude_oil_enhanced': {
        'indicator_periods': {
            'RSI_PERIOD': [10, 12, 14, 16, 18],
            'MACD_FAST': [10, 12, 14],
            'MACD_SLOW': [24, 26, 28],
            'MACD_SIGNAL': [7, 9, 11],
            'ADX_PERIOD': [12, 14, 16],
            'ATR_PERIOD': [12, 14, 16],
            'BB_PERIOD': [18, 20, 22],
            'BB_STD': [1.8, 2.0, 2.2],
            'EMA_FAST': [7, 9, 11],
            'EMA_SLOW': [19, 21, 23],
            'EMA_LONG': [45, 50, 55],
            'VWAP_PERIOD': [18, 20, 22]
        },
        'entry_thresholds': {
            'BASE_ENTRY_THRESHOLD': [50, 55, 58, 60, 65],
            'MIN_ENTRY_THRESHOLD': [45, 48, 50],
            'MAX_ENTRY_THRESHOLD': [68, 72, 75],
            'ADX_ADAPTIVE_FACTOR': [0.30, 0.35, 0.40],
            'AI_CONFIDENCE_MULTIPLIER': [0.15, 0.18, 0.20]
        },
        'risk_management': {
            'ATR_SL_MULTIPLIER': [1.5, 1.8, 2.0, 2.5],
            'ATR_TP_MULTIPLIER': [2.5, 3.0, 3.5, 4.0],
            'TRAILING_STOP_ATR': [1.0, 1.2, 1.5],
            'BREAKEVEN_ATR': [1.0, 1.2, 1.5]
        },
        'timeframe_weights': {
            '5m': [0.15, 0.20, 0.25],
            '15m': [0.50, 0.60, 0.70],
            '1h': [0.10, 0.15, 0.20]
        },
        'trending_weights': {
            'MACD': [0.25, 0.30, 0.35],
            'ADX': [0.18, 0.20, 0.22],
            'RSI': [0.12, 0.15, 0.18],
            'BOLLINGER': [0.12, 0.15, 0.18],
            'EMA_CROSS': [0.10, 0.12, 0.14],
            'VOLUME': [0.06, 0.08, 0.10],
            'VWAP': [0.00]
        },
        'ranging_weights': {
            'RSI': [0.25, 0.30, 0.35],
            'BOLLINGER': [0.25, 0.30, 0.35],
            'VOLUME': [0.15, 0.20, 0.25],
            'VWAP': [0.08, 0.10, 0.12],
            'EMA_CROSS': [0.03, 0.05, 0.07],
            'MACD': [0.03, 0.05, 0.07]
        },
        'position_sizing': {
            'BASE_QUANTITY': [1],
            'MAX_POSITION_SIZE': [2],
            'RISK_PER_TRADE_PCT': [1.0, 1.5, 2.0]
        }
    }
}

# Key parameters for grid search (reduced search space)
GRID_SEARCH_PARAMS = {
    'natural_gas_clawdbot': {
        'BASE_ENTRY_THRESHOLD': [50, 55, 60, 65, 70],
        'MIN_ENTRY_THRESHOLD': [45, 50, 55],
        'ATR_SL_MULTIPLIER': [2.0, 2.5, 3.0],
        'ATR_TP_MULTIPLIER': [3.5, 4.0, 4.5, 5.0],
        'TIMEFRAME_15m': [0.40, 0.50, 0.60, 0.70],
        'ADX_ADAPTIVE_FACTOR': [0.3, 0.4, 0.5]
    },
    'crude_oil_enhanced': {
        'BASE_ENTRY_THRESHOLD': [50, 55, 58, 60, 65],
        'MIN_ENTRY_THRESHOLD': [45, 48, 50],
        'ATR_SL_MULTIPLIER': [1.5, 1.8, 2.0, 2.5],
        'ATR_TP_MULTIPLIER': [2.5, 3.0, 3.5, 4.0],
        'TIMEFRAME_15m': [0.50, 0.60, 0.70],
        'ADX_ADAPTIVE_FACTOR': [0.30, 0.35, 0.40]
    }
}

def get_parameter_ranges(strategy_name: str) -> Dict[str, Dict[str, List]]:
    """Get parameter ranges for a strategy"""
    return PARAMETER_SPACES.get(strategy_name, {})

def get_grid_search_params(strategy_name: str) -> Dict[str, List]:
    """Get key parameters for grid search"""
    return GRID_SEARCH_PARAMS.get(strategy_name, {})

def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Normalize weights to sum to 1.0"""
    total = sum(weights.values())
    if total == 0:
        return weights
    return {k: v / total for k, v in weights.items()}

def normalize_timeframe_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Normalize timeframe weights to sum to 1.0"""
    return normalize_weights(weights)

def get_continuous_ranges(strategy_name: str) -> Dict[str, Tuple[float, float]]:
    """Get continuous parameter ranges for Bayesian optimization"""
    spaces = {
        'natural_gas_clawdbot': {
            'RSI_PERIOD': (10, 18),
            'MACD_FAST': (10, 14),
            'MACD_SLOW': (24, 28),
            'ADX_PERIOD': (12, 16),
            'BASE_ENTRY_THRESHOLD': (50, 70),
            'MIN_ENTRY_THRESHOLD': (45, 55),
            'MAX_ENTRY_THRESHOLD': (70, 80),
            'ADX_ADAPTIVE_FACTOR': (0.3, 0.5),
            'ATR_SL_MULTIPLIER': (2.0, 3.0),
            'ATR_TP_MULTIPLIER': (3.5, 5.0),
            'TIMEFRAME_15m': (0.40, 0.70),
            'TIMEFRAME_5m': (0.20, 0.40),
            'TIMEFRAME_1h': (0.10, 0.30),
            'TRENDING_MACD': (0.20, 0.30),
            'TRENDING_ADX': (0.20, 0.30),
            'TRENDING_RSI': (0.10, 0.20)
        },
        'crude_oil_enhanced': {
            'RSI_PERIOD': (10, 18),
            'MACD_FAST': (10, 14),
            'MACD_SLOW': (24, 28),
            'ADX_PERIOD': (12, 16),
            'BASE_ENTRY_THRESHOLD': (50, 65),
            'MIN_ENTRY_THRESHOLD': (45, 50),
            'MAX_ENTRY_THRESHOLD': (68, 75),
            'ADX_ADAPTIVE_FACTOR': (0.30, 0.40),
            'ATR_SL_MULTIPLIER': (1.5, 2.5),
            'ATR_TP_MULTIPLIER': (2.5, 4.0),
            'TIMEFRAME_15m': (0.50, 0.70),
            'TIMEFRAME_5m': (0.15, 0.25),
            'TIMEFRAME_1h': (0.10, 0.20),
            'TRENDING_MACD': (0.25, 0.35),
            'TRENDING_ADX': (0.18, 0.22),
            'TRENDING_RSI': (0.12, 0.18)
        }
    }
    return spaces.get(strategy_name, {})
