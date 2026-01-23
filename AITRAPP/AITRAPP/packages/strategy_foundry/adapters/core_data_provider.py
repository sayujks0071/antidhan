"""
Core Data Provider Adapter
"""
# Placeholder if core has a unified data provider.
# Currently strategy foundry uses its own loader/source logic but this is here for future linkage.
from typing import Optional
import pandas as pd

class CoreDataProvider:
    @staticmethod
    def get_ohlcv(symbol: str, timeframe: str, start=None, end=None) -> Optional[pd.DataFrame]:
        # Implement call to packages.core.historical_data if it supports what we need
        # For now, return None to trigger fallback to Yahoo downloader
        return None
