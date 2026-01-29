"""
Walk-Forward Optimization Engine
--------------------------------
Implements Walk-Forward Analysis (WFA) to validate strategy robustness
and detect overfitting by testing on out-of-sample data.
"""
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import sys
from pathlib import Path

# Add utils to path
utils_path = Path(__file__).parent
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))

from simple_backtest_engine import SimpleBacktestEngine
from optimization_engine import GridSearchOptimizer, BayesianOptimizer, calculate_composite_score
from strategy_param_injector import create_strategy_with_params

logger = logging.getLogger("WalkForwardEngine")

class WalkForwardOptimizer:
    """
    Performs Walk-Forward Analysis on a strategy.

    Methodology:
    1. Divide history into rolling windows (Train + Test).
    2. For each window:
       a. Optimize parameters on 'Train' data.
       b. Apply best parameters to 'Test' (Out-of-Sample) data.
    3. Aggregate 'Test' results to form the Walk-Forward Equity Curve.
    """

    def __init__(self, strategy_name: str, symbol: str, exchange: str,
                 start_date: str, end_date: str,
                 train_window_months: int = 6,
                 test_window_months: int = 3,
                 initial_capital: float = 1000000.0,
                 api_key: str = None, host: str = "http://127.0.0.1:5001"):

        self.strategy_name = strategy_name
        self.symbol = symbol
        self.exchange = exchange
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)

        self.train_window = pd.DateOffset(months=train_window_months)
        self.test_window = pd.DateOffset(months=test_window_months)

        self.initial_capital = initial_capital
        self.api_key = api_key
        self.host = host

        self.results = []
        self.aggregated_trades = []
        self.equity_curve = []

    def generate_windows(self) -> List[Dict[str, datetime]]:
        """Generate (Train Start, Train End, Test Start, Test End) tuples"""
        windows = []
        current_train_start = self.start_date

        while True:
            train_end = current_train_start + self.train_window
            test_start = train_end + timedelta(days=1) # Start test next day
            test_end = test_start + self.test_window

            if test_end > self.end_date:
                break

            windows.append({
                'train_start': current_train_start,
                'train_end': train_end,
                'test_start': test_start,
                'test_end': test_end
            })

            # Slide forward by test_window length
            current_train_start = current_train_start + self.test_window

        return windows

    def run(self, optimization_method: str = 'grid', max_evals: int = 20) -> Dict[str, Any]:
        """
        Run the Walk-Forward Analysis.

        Args:
            optimization_method: 'grid' or 'bayesian'
            max_evals: Max evaluations per training window
        """
        windows = self.generate_windows()
        logger.info(f"Generated {len(windows)} Walk-Forward windows.")

        current_capital = self.initial_capital

        overall_stats = {
            'wins': 0, 'losses': 0, 'total_pnl': 0.0, 'trades': 0
        }

        for i, window in enumerate(windows, 1):
            train_start_str = window['train_start'].strftime("%Y-%m-%d")
            train_end_str = window['train_end'].strftime("%Y-%m-%d")
            test_start_str = window['test_start'].strftime("%Y-%m-%d")
            test_end_str = window['test_end'].strftime("%Y-%m-%d")

            logger.info(f"Processing Window {i}/{len(windows)}")
            logger.info(f"  Train: {train_start_str} to {train_end_str}")
            logger.info(f"  Test:  {test_start_str} to {test_end_str}")

            # 1. Optimize on In-Sample (Train) Data
            best_params = {}
            if optimization_method == 'bayesian':
                opt = BayesianOptimizer(
                    self.strategy_name, self.symbol, self.exchange,
                    train_start_str, train_end_str,
                    initial_capital=current_capital,
                    api_key=self.api_key, host=self.host
                )
                res = opt.optimize(n_iterations=max_evals)
                best_params = res.get('best_parameters', {})
            else:
                opt = GridSearchOptimizer(
                    self.strategy_name, self.symbol, self.exchange,
                    train_start_str, train_end_str,
                    initial_capital=current_capital,
                    api_key=self.api_key, host=self.host
                )
                res = opt.optimize(max_combinations=max_evals)
                if res:
                    best_params = res[0].get('parameters', {})

            if not best_params:
                logger.warning(f"  No best parameters found for Window {i}. Using defaults.")
                # Could fetch defaults from strategy...

            logger.info(f"  Best Params: {best_params}")

            # 2. Test on Out-of-Sample (Test) Data using Best Params
            strategy_module = create_strategy_with_params(self.strategy_name, best_params)
            engine = SimpleBacktestEngine(
                initial_capital=current_capital,
                api_key=self.api_key,
                host=self.host
            )

            test_result = engine.run_backtest(
                strategy_module, self.symbol, self.exchange,
                test_start_str, test_end_str
            )

            # 3. Collect Results
            metrics = test_result.get('metrics', {})
            trades = test_result.get('closed_trades', [])

            # Update running capital from the test result
            # Note: The engine resets capital, so we calculate delta
            period_pnl = test_result.get('final_capital', current_capital) - current_capital
            current_capital += period_pnl

            self.results.append({
                'window': i,
                'train_period': f"{train_start_str} to {train_end_str}",
                'test_period': f"{test_start_str} to {test_end_str}",
                'best_params': best_params,
                'metrics': metrics,
                'pnl': period_pnl
            })

            self.aggregated_trades.extend(trades)

            # Stats update
            overall_stats['total_pnl'] += period_pnl
            overall_stats['trades'] += len(trades)

            logger.info(f"  Window P&L: ₹{period_pnl:,.2f} | Cumulative: ₹{overall_stats['total_pnl']:,.2f}")

        # Final Compilation
        robustness_score = self.calculate_robustness()

        return {
            'strategy': self.strategy_name,
            'symbol': self.symbol,
            'total_windows': len(windows),
            'final_capital': current_capital,
            'total_return': current_capital - self.initial_capital,
            'robustness_score': robustness_score,
            'window_results': self.results,
            'aggregated_trades_count': len(self.aggregated_trades)
        }

    def calculate_robustness(self) -> float:
        """
        Calculate a Robustness Score (0-100).
        Based on:
        - Percentage of profitable Walk-Forward windows
        - Consistency of returns
        """
        if not self.results: return 0.0

        profitable_windows = sum(1 for r in self.results if r['pnl'] > 0)
        win_rate_windows = (profitable_windows / len(self.results)) * 100

        # consistency penalty? (std dev of returns)

        return win_rate_windows
