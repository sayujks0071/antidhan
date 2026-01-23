"""Backtest configuration"""
from datetime import datetime
from typing import List, Dict

# Default backtest parameters
DEFAULT_START_DATE = datetime(2025, 8, 15)
DEFAULT_END_DATE = datetime(2025, 11, 10)
DEFAULT_INITIAL_CAPITAL = 1000000.0  # 10 lakh

# Default symbols to test
DEFAULT_SYMBOLS = ["NIFTY"]

# Ranking weights (must sum to 1.0)
RANKING_WEIGHTS = {
    "total_return_pct": 0.30,
    "win_rate": 0.20,
    "profit_factor": 0.25,
    "max_drawdown_pct": 0.15,  # Inverse (lower is better)
    "total_trades": 0.10,  # Normalized
}

# Strategy selection
# Empty list means test all strategies
SELECTED_STRATEGIES: List[str] = []

# Output paths
OUTPUT_DIR = "openalgo/strategies/backtest_results"
RESULTS_JSON = f"{OUTPUT_DIR}/backtest_results.json"
RESULTS_CSV = f"{OUTPUT_DIR}/backtest_results.csv"
RANKINGS_CSV = f"{OUTPUT_DIR}/strategy_rankings.csv"

# Backtest settings
BACKTEST_SETTINGS = {
    "initial_capital": DEFAULT_INITIAL_CAPITAL,
    "start_date": DEFAULT_START_DATE,
    "end_date": DEFAULT_END_DATE,
    "symbols": DEFAULT_SYMBOLS,
    "ranking_weights": RANKING_WEIGHTS,
}
