"""
Data Quality & Validation Utilities
-----------------------------------
Ensures integrity of market data before use in backtesting or live trading.
"""
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("DataValidator")

class DataValidator:
    """
    Validates OHLCV DataFrame for common data quality issues.
    """

    @staticmethod
    def validate_ohlcv(df: pd.DataFrame,
                       symbol: str = "Unknown",
                       interval_minutes: int = 15) -> Dict[str, Any]:
        """
        Run comprehensive validation on OHLCV data.

        Args:
            df: DataFrame with Open, High, Low, Close, Volume
            symbol: Symbol name for reporting
            interval_minutes: Expected time interval in minutes

        Returns:
            Dictionary with validation results
        """
        results = {
            'is_valid': True,
            'issues': [],
            'stats': {}
        }

        if df.empty:
            results['is_valid'] = False
            results['issues'].append("DataFrame is empty")
            return results

        # Standardize columns
        df.columns = [c.lower() for c in df.columns]
        required = ['open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required if c not in df.columns]

        if missing:
            results['is_valid'] = False
            results['issues'].append(f"Missing columns: {missing}")
            return results

        # 1. Missing Values (NaN)
        nan_counts = df[required].isna().sum().sum()
        if nan_counts > 0:
            results['issues'].append(f"Found {nan_counts} NaN values")
            # We treat this as a warning unless it's excessive
            if nan_counts > len(df) * 0.1:
                results['is_valid'] = False

        # 2. Zero or Negative Prices
        invalid_prices = (df[['open', 'high', 'low', 'close']] <= 0).sum().sum()
        if invalid_prices > 0:
            results['is_valid'] = False
            results['issues'].append(f"Found {invalid_prices} zero/negative prices")

        # 3. High/Low Consistency
        inconsistent_hl = (df['high'] < df['low']).sum()
        if inconsistent_hl > 0:
            results['is_valid'] = False
            results['issues'].append(f"Found {inconsistent_hl} bars where High < Low")

        # 4. Price Spikes (> 20% in one bar)
        # Check High/Low relative to Open
        pct_change = (df['high'] - df['low']) / df['open']
        spikes = (pct_change > 0.20).sum()
        if spikes > 0:
            results['issues'].append(f"Found {spikes} extreme price spikes (>20% intraday)")

        # 5. Time Gaps
        # Calculate time diffs
        if isinstance(df.index, pd.DatetimeIndex):
            time_diffs = df.index.to_series().diff()
            # Expected diff
            expected = pd.Timedelta(minutes=interval_minutes)
            # Allow some tolerance for weekends/overnight, but warn on frequent gaps
            # Simply check median diff
            median_diff = time_diffs.median()
            if median_diff > expected * 1.5:
                results['issues'].append(f"Irregular timestamps. Median diff: {median_diff}")

        results['stats'] = {
            'rows': len(df),
            'start': str(df.index[0]),
            'end': str(df.index[-1]),
            'nan_count': int(nan_counts),
            'spikes': int(spikes)
        }

        return results
