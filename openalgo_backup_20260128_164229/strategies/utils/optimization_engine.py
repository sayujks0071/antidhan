"""
Optimization Engine for Strategy Parameters
-------------------------------------------
Implements grid search and Bayesian optimization for finding optimal strategy parameters.
"""
import os
import sys
import logging
import json
import itertools
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np
from pathlib import Path

# Add utils to path
utils_path = Path(__file__).parent
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))

from simple_backtest_engine import SimpleBacktestEngine
from strategy_param_injector import create_strategy_with_params, get_strategy_symbol
from parameter_space import get_grid_search_params, get_continuous_ranges, normalize_weights, normalize_timeframe_weights

logger = logging.getLogger("OptimizationEngine")

# Try to import scikit-optimize for Bayesian optimization
try:
    from skopt import gp_minimize, forest_minimize
    from skopt.space import Real, Integer
    from skopt.utils import use_named_args
    SKOPT_AVAILABLE = True
except ImportError:
    SKOPT_AVAILABLE = False
    logger.warning("scikit-optimize not available, Bayesian optimization will use random search fallback")

def calculate_composite_score(metrics: Dict[str, Any]) -> float:
    """
    Calculate composite score for ranking strategies.
    Higher is better.
    
    Args:
        metrics: Dictionary with performance metrics
    
    Returns:
        Composite score (0-100 scale)
    """
    total_return_pct = metrics.get('total_return_pct', 0)
    win_rate = metrics.get('win_rate', 0)
    profit_factor = metrics.get('profit_factor', 0)
    max_drawdown_pct = metrics.get('max_drawdown_pct', 0)
    total_trades = metrics.get('total_trades', 0)
    
    # Normalize components
    return_score = min(max(total_return_pct / 50.0, 0), 1.0) * 100  # Cap at 50% return
    win_rate_score = win_rate / 100.0  # Already in percentage
    profit_factor_score = min(max(profit_factor / 3.0, 0), 1.0)  # Cap at 3.0
    drawdown_score = max(0, (100 - max_drawdown_pct) / 100.0)  # Inverse (lower is better)
    trades_score = min(total_trades / 50.0, 1.0)  # Encourage at least 50 trades
    
    composite = (
        return_score * 0.30 +
        win_rate_score * 100 * 0.20 +
        profit_factor_score * 100 * 0.25 +
        drawdown_score * 100 * 0.15 +
        trades_score * 100 * 0.10
    )
    
    return composite

class GridSearchOptimizer:
    """Grid search optimizer for strategy parameters"""
    
    def __init__(self, strategy_name: str, symbol: str, exchange: str, 
                 start_date: str, end_date: str, initial_capital: float = 1000000.0,
                 api_key: str = None, host: str = "http://127.0.0.1:5001"):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.exchange = exchange
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY', 'demo_key')
        self.host = host
        
        self.results: List[Dict[str, Any]] = []
    
    def generate_combinations(self, param_ranges: Dict[str, List]) -> List[Dict[str, Any]]:
        """Generate all parameter combinations for grid search"""
        keys = list(param_ranges.keys())
        values = list(param_ranges.values())
        
        combinations = []
        for combo in itertools.product(*values):
            combinations.append(dict(zip(keys, combo)))
        
        return combinations
    
    def run_backtest_with_params(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Run backtest with given parameters"""
        try:
            # Create strategy module with injected parameters
            strategy_module = create_strategy_with_params(self.strategy_name, parameters)
            
            # Initialize backtest engine
            engine = SimpleBacktestEngine(
                initial_capital=self.initial_capital,
                api_key=self.api_key,
                host=self.host
            )
            
            # Run backtest
            results = engine.run_backtest(
                strategy_module=strategy_module,
                symbol=self.symbol,
                exchange=self.exchange,
                start_date=self.start_date,
                end_date=self.end_date,
                interval="15m"
            )
            
            if 'error' in results:
                return {
                    'parameters': parameters,
                    'error': results['error'],
                    'composite_score': 0.0
                }
            
            # Calculate composite score
            metrics = results.get('metrics', {})
            composite_score = calculate_composite_score(metrics)
            
            return {
                'parameters': parameters,
                'metrics': metrics,
                'composite_score': composite_score,
                'total_trades': results.get('total_trades', 0),
                'final_capital': results.get('final_capital', self.initial_capital)
            }
        
        except Exception as e:
            logger.error(f"Error running backtest with params {parameters}: {e}")
            return {
                'parameters': parameters,
                'error': str(e),
                'composite_score': 0.0
            }
    
    def optimize(self, max_combinations: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Run grid search optimization.
        
        Args:
            max_combinations: Maximum number of combinations to test (None = all)
        
        Returns:
            List of results sorted by composite score (best first)
        """
        logger.info(f"Starting grid search for {self.strategy_name}")
        
        # Get parameter ranges for grid search
        param_ranges = get_grid_search_params(self.strategy_name)
        
        if not param_ranges:
            logger.error(f"No grid search parameters defined for {self.strategy_name}")
            return []
        
        # Generate all combinations
        combinations = self.generate_combinations(param_ranges)
        
        if max_combinations and len(combinations) > max_combinations:
            logger.info(f"Limiting to {max_combinations} combinations (total: {len(combinations)})")
            # Sample randomly
            import random
            combinations = random.sample(combinations, max_combinations)
        
        logger.info(f"Testing {len(combinations)} parameter combinations...")
        
        # Run backtests
        for i, params in enumerate(combinations, 1):
            logger.info(f"Testing combination {i}/{len(combinations)}: {params}")
            result = self.run_backtest_with_params(params)
            self.results.append(result)
            
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{len(combinations)} combinations tested")
        
        # Sort by composite score (best first)
        self.results.sort(key=lambda x: x.get('composite_score', 0), reverse=True)
        
        logger.info(f"Grid search complete. Best score: {self.results[0].get('composite_score', 0):.2f}")
        
        return self.results
    
    def get_best_parameters(self, top_n: int = 1) -> List[Dict[str, Any]]:
        """Get top N best parameter configurations"""
        valid_results = [r for r in self.results if 'error' not in r]
        return valid_results[:top_n]

class BayesianOptimizer:
    """Bayesian optimization for strategy parameters"""
    
    def __init__(self, strategy_name: str, symbol: str, exchange: str,
                 start_date: str, end_date: str, initial_capital: float = 1000000.0,
                 api_key: str = None, host: str = "http://127.0.0.1:5001",
                 initial_params: Optional[Dict[str, Any]] = None):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.exchange = exchange
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY', 'demo_key')
        self.host = host
        self.initial_params = initial_params or {}
        
        self.history: List[Dict[str, Any]] = []
        self.best_score = -float('inf')
        self.best_params = None
    
    def objective_function(self, param_values: List[float], param_names: List[str]) -> float:
        """
        Objective function for Bayesian optimization.
        Returns negative composite score (for minimization).
        
        Args:
            param_values: Parameter values from optimizer
            param_names: Parameter names
        
        Returns:
            Negative composite score (minimize = maximize score)
        """
        # Convert parameter values to dictionary
        params = dict(zip(param_names, param_values))
        
        # Round integer parameters
        int_params = ['RSI_PERIOD', 'MACD_FAST', 'MACD_SLOW', 'MACD_SIGNAL', 
                     'ADX_PERIOD', 'ATR_PERIOD', 'BB_PERIOD', 'EMA_FAST', 
                     'EMA_SLOW', 'EMA_LONG', 'VWAP_PERIOD']
        for key in int_params:
            if key in params:
                params[key] = int(round(params[key]))
        
        # Handle timeframe weights normalization
        if 'TIMEFRAME_15m' in params or 'TIMEFRAME_5m' in params or 'TIMEFRAME_1h' in params:
            tf_weights = {}
            if 'TIMEFRAME_15m' in params:
                tf_weights['15m'] = params['TIMEFRAME_15m']
            if 'TIMEFRAME_5m' in params:
                tf_weights['5m'] = params['TIMEFRAME_5m']
            if 'TIMEFRAME_1h' in params:
                tf_weights['1h'] = params['TIMEFRAME_1h']
            
            total = sum(tf_weights.values())
            if total > 0:
                tf_weights = {k: v / total for k, v in tf_weights.items()}
            else:
                tf_weights = {'5m': 0.25, '15m': 0.50, '1h': 0.25}
            
            params['TIMEFRAME_WEIGHTS'] = tf_weights
            for key in list(params.keys()):
                if key.startswith('TIMEFRAME_'):
                    del params[key]
        
        try:
            # Run backtest
            strategy_module = create_strategy_with_params(self.strategy_name, params)
            
            engine = SimpleBacktestEngine(
                initial_capital=self.initial_capital,
                api_key=self.api_key,
                host=self.host
            )
            
            results = engine.run_backtest(
                strategy_module=strategy_module,
                symbol=self.symbol,
                exchange=self.exchange,
                start_date=self.start_date,
                end_date=self.end_date,
                interval="15m"
            )
            
            if 'error' in results:
                return 1000.0  # Large penalty for errors
            
            metrics = results.get('metrics', {})
            composite_score = calculate_composite_score(metrics)
            
            # Track history
            self.history.append({
                'parameters': params.copy(),
                'composite_score': composite_score,
                'metrics': metrics,
                'iteration': len(self.history) + 1
            })
            
            # Update best
            if composite_score > self.best_score:
                self.best_score = composite_score
                self.best_params = params.copy()
            
            # Return negative for minimization
            return -composite_score
        
        except Exception as e:
            logger.error(f"Error in objective function: {e}")
            return 1000.0
    
    def optimize(self, n_iterations: int = 50, n_initial_points: int = 10) -> Dict[str, Any]:
        """
        Run Bayesian optimization.
        
        Args:
            n_iterations: Number of optimization iterations
            n_initial_points: Number of random initial points
        
        Returns:
            Best parameters and score
        """
        if not SKOPT_AVAILABLE:
            logger.warning("scikit-optimize not available, using random search fallback")
            return self._random_search(n_iterations)
        
        logger.info(f"Starting Bayesian optimization for {self.strategy_name}")
        
        # Get continuous parameter ranges
        param_ranges = get_continuous_ranges(self.strategy_name)
        
        if not param_ranges:
            logger.error(f"No continuous ranges defined for {self.strategy_name}")
            return {'error': 'No parameter ranges defined'}
        
        # Build search space
        dimensions = []
        param_names = []
        
        for param_name, (low, high) in param_ranges.items():
            if 'PERIOD' in param_name or param_name in ['MACD_FAST', 'MACD_SLOW', 'MACD_SIGNAL']:
                dimensions.append(Integer(low=int(low), high=int(high), name=param_name))
            else:
                dimensions.append(Real(low=low, high=high, name=param_name))
            param_names.append(param_name)
        
        # Create objective function with named parameters
        @use_named_args(dimensions=dimensions)
        def objective(**kwargs):
            param_values = [kwargs[name] for name in param_names]
            return self.objective_function(param_values, param_names)
        
        # Run optimization
        try:
            result = gp_minimize(
                func=objective,
                dimensions=dimensions,
                n_calls=n_iterations,
                n_initial_points=n_initial_points,
                random_state=42,
                acq_func='EI'  # Expected Improvement
            )
            
            # Extract best parameters
            best_params_dict = {}
            for i, name in enumerate(param_names):
                best_params_dict[name] = result.x[i]
            
            # Round integer parameters
            int_params = ['RSI_PERIOD', 'MACD_FAST', 'MACD_SLOW', 'MACD_SIGNAL',
                         'ADX_PERIOD', 'ATR_PERIOD', 'BB_PERIOD', 'EMA_FAST',
                         'EMA_SLOW', 'EMA_LONG', 'VWAP_PERIOD']
            for key in int_params:
                if key in best_params_dict:
                    best_params_dict[key] = int(round(best_params_dict[key]))
            
            return {
                'best_parameters': best_params_dict,
                'best_score': -result.fun,  # Convert back to positive
                'n_iterations': len(result.func_vals),
                'history': self.history
            }
        
        except Exception as e:
            logger.error(f"Bayesian optimization error: {e}")
            return {'error': str(e)}
    
    def _random_search(self, n_iterations: int) -> Dict[str, Any]:
        """Fallback random search if scikit-optimize not available"""
        logger.info(f"Running random search (fallback) for {n_iterations} iterations")
        
        param_ranges = get_continuous_ranges(self.strategy_name)
        
        for i in range(n_iterations):
            # Generate random parameters
            params = {}
            for param_name, (low, high) in param_ranges.items():
                if 'PERIOD' in param_name or param_name in ['MACD_FAST', 'MACD_SLOW', 'MACD_SIGNAL']:
                    params[param_name] = int(np.random.uniform(low, high))
                else:
                    params[param_name] = np.random.uniform(low, high)
            
            # Run backtest
            try:
                strategy_module = create_strategy_with_params(self.strategy_name, params)
                engine = SimpleBacktestEngine(
                    initial_capital=self.initial_capital,
                    api_key=self.api_key,
                    host=self.host
                )
                
                results = engine.run_backtest(
                    strategy_module=strategy_module,
                    symbol=self.symbol,
                    exchange=self.exchange,
                    start_date=self.start_date,
                    end_date=self.end_date,
                    interval="15m"
                )
                
                if 'error' not in results:
                    metrics = results.get('metrics', {})
                    composite_score = calculate_composite_score(metrics)
                    
                    self.history.append({
                        'parameters': params.copy(),
                        'composite_score': composite_score,
                        'metrics': metrics,
                        'iteration': i + 1
                    })
                    
                    if composite_score > self.best_score:
                        self.best_score = composite_score
                        self.best_params = params.copy()
            
            except Exception as e:
                logger.debug(f"Random search iteration {i+1} failed: {e}")
        
        return {
            'best_parameters': self.best_params,
            'best_score': self.best_score,
            'n_iterations': n_iterations,
            'history': self.history
        }
