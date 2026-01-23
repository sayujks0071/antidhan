import os
import pandas as pd
import yaml
import logging
from datetime import datetime, timedelta
import pytz
from typing import Optional, Dict

from packages.strategy_foundry.data.sources import YahooSource

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'configs', 'foundry.yaml')
INSTRUMENT_MAP_PATH = os.path.join(BASE_DIR, 'configs', 'instrument_map.yaml')
CACHE_DIR = os.path.join(BASE_DIR, 'data', 'cache')

IST = pytz.timezone('Asia/Kolkata')

class DataLoader:
    def __init__(self):
        self.source = YahooSource()
        self.cache_dir = CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)

        # Load configs
        self.foundry_config = self._load_yaml(CONFIG_PATH).get('foundry', {})
        self.instrument_map = self._load_yaml(INSTRUMENT_MAP_PATH)

        self.proxies = self.instrument_map.get('paper_proxy', {}) # Use paper proxy as fallback source

    def _load_yaml(self, path):
        if not os.path.exists(path):
            return {}
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def _get_cache_path(self, symbol: str, interval: str) -> str:
        # Sanitize symbol for filename
        safe_symbol = symbol.replace('^', '').replace('.', '_')
        return os.path.join(self.cache_dir, f"{safe_symbol}_{interval}.csv")

    def _is_cache_valid(self, path: str) -> bool:
        if not os.path.exists(path):
            return False

        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        # Valid if less than 4 hours old (for hourly runs)
        # Or maybe just "today"?
        # Intraday data updates frequently. 1 hour validity?
        # The prompt says "hourly".
        if datetime.now() - mtime < timedelta(minutes=55):
            return True
        return False

    def get_data(self, instrument: str, interval: str = "1d", force_download: bool = False) -> Optional[pd.DataFrame]:
        """
        Get data for an instrument (e.g. 'NIFTY').
        Handles mapping to symbol (^NSEI), caching, and fallback to proxy.
        """
        # 1. Resolve primary symbol
        research_map = self.instrument_map.get('research', {})
        symbol = research_map.get(instrument, instrument)

        df = self._get_data_for_symbol(symbol, interval, force_download)

        # 2. Fallback if failed and we have a proxy
        if (df is None or df.empty) and instrument in self.proxies:
            proxy_symbol = self.proxies[instrument]
            # Need to append extension for Yahoo if not present (e.g. NIFTYBEES -> NIFTYBEES.NS)
            if not proxy_symbol.endswith('.NS') and not proxy_symbol.startswith('^'):
                proxy_symbol += '.NS'

            logger.warning(f"Falling back to proxy {proxy_symbol} for {instrument} {interval}")
            df = self._get_data_for_symbol(proxy_symbol, interval, force_download)

        if df is not None and not df.empty:
            # Normalize to IST
            if df['datetime'].dt.tz is None:
                df['datetime'] = df['datetime'].dt.tz_localize('UTC') # Assume UTC if naive

            df['datetime'] = df['datetime'].dt.tz_convert(IST)

            # Filter Market Hours?
            # 5m/15m might have pre-market data? Yahoo usually includes it?
            # We filter 09:15 to 15:30
            if interval in ['5m', '15m']:
                df = df[
                    (df['datetime'].dt.time >= datetime.strptime("09:15", "%H:%M").time()) &
                    (df['datetime'].dt.time <= datetime.strptime("15:30", "%H:%M").time())
                ]

            df.reset_index(drop=True, inplace=True)

        return df

    def _get_data_for_symbol(self, symbol: str, interval: str, force_download: bool) -> Optional[pd.DataFrame]:
        cache_path = self._get_cache_path(symbol, interval)

        if not force_download and self._is_cache_valid(cache_path):
            try:
                logger.info(f"Loading {symbol} ({interval}) from cache")
                df = pd.read_csv(cache_path)
                df['datetime'] = pd.to_datetime(df['datetime']) # UTC aware usually from read_csv if saved that way?
                # pd.to_datetime might lose tz if not careful.
                # When we save, we should use iso format.
                return df
            except Exception as e:
                logger.error(f"Cache read error for {symbol}: {e}")

        # Download
        days = self.foundry_config.get('data_days_intraday', 59) if interval in ['5m', '15m'] else self.foundry_config.get('data_days_daily', 3650)

        df = self.source.download(symbol, interval, days)

        if df is not None:
            # Save to cache
            df.to_csv(cache_path, index=False)
        elif os.path.exists(cache_path):
            # Fallback to stale cache
            logger.warning(f"Download failed for {symbol}, using stale cache")
            try:
                df = pd.read_csv(cache_path)
                df['datetime'] = pd.to_datetime(df['datetime'])
            except:
                pass

        return df

if __name__ == "__main__":
    loader = DataLoader()
    df = loader.get_data("NIFTY", "5m")
    if df is not None:
        print(df.head())
        print(df.tail())
