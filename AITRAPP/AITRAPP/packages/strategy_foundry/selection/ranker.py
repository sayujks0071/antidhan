import pandas as pd
import numpy as np
from typing import List, Dict

class Ranker:
    @staticmethod
    def rank(results: List[Dict], timeframe_weights: Dict = None) -> pd.DataFrame:
        """
        Ranks candidates based on OOS metrics.
        results: List of dicts, each containing 'strategy' (Config) and 'metrics' (List of fold metrics).
        """
        if not results:
            return pd.DataFrame()

        rows = []
        for res in results:
            strat = res['strategy']
            fold_metrics = res['metrics']

            # Aggregate Fold Metrics
            avg_sharpe = np.mean([m['sharpe'] for m in fold_metrics])
            avg_calmar = np.mean([m['calmar'] for m in fold_metrics])
            avg_return = np.mean([m['avg_return'] for m in fold_metrics])
            avg_max_dd = np.mean([m['max_dd'] for m in fold_metrics])

            # Stability (Variance of Sharpe)
            sharpes = [m['sharpe'] for m in fold_metrics]
            stability = 1.0 / (np.std(sharpes) + 0.1) # Higher is better

            # Count Positive Folds
            positive_folds = sum(1 for m in fold_metrics if m['avg_return'] > 0)

            # Score Calculation
            # Normalize? Or raw sum?
            # Raw sum is easier for relative ranking.
            # Weights: 25% Sharpe, 25% Calmar, 20% Return, 15% Stability

            score = (0.25 * avg_sharpe) + (0.25 * avg_calmar) + (20.0 * avg_return) + (0.15 * stability)

            # Sanity Bonus/Penalty (already applied to Sharpe in WF, but explicit here)
            # Intraday Sanity: 5% (handled via Sharpe penalty in WF)

            row = {
                "strategy_id": strat.strategy_id,
                "score": score,
                "avg_sharpe": avg_sharpe,
                "avg_calmar": avg_calmar,
                "avg_return": avg_return,
                "avg_max_dd": avg_max_dd,
                "stability": stability,
                "positive_folds": positive_folds,
                "total_trades": sum(m['total_trades'] for m in fold_metrics),
                "strategy_config": strat.to_dict()
            }
            rows.append(row)

        df = pd.DataFrame(rows)

        # Sort by Score
        df.sort_values('score', ascending=False, inplace=True)
        return df

    @staticmethod
    def filter_candidates(df: pd.DataFrame, min_trades: int = 50, min_folds: int = 3) -> pd.DataFrame:
        """
        Applies gating criteria.
        """
        if df.empty:
            return df

        mask = (
            (df['total_trades'] >= min_trades) &
            (df['positive_folds'] >= min_folds) &
            (df['avg_max_dd'] <= 0.30) &
            (df['avg_sharpe'] > 0.5) # Basic quality
        )
        return df[mask]
