import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

logger = logging.getLogger(__name__)

OPENALGO_BASE_URL = "http://127.0.0.1:5001/api/v1"

class MCXSource:
    """
    Data source for MCX commodities via OpenAlgo API.
    Supports 5m, 15m, 1h intervals for commodity futures.
    """

    def __init__(self, api_key: str = None):
        """
        Initialize MCX data source.

        Args:
            api_key: OpenAlgo API key (if not provided, reads from environment)
        """
        import os
        self.api_key = api_key or os.getenv("OPENALGO_APIKEY")
        if not self.api_key:
            raise ValueError("OPENALGO_APIKEY must be set in environment or passed to constructor")

        self.exchange = "MCX"
        self.cache = {}  # Symbol -> (timestamp, dataframe)
        self.cache_ttl = 55 * 60  # 55 minutes like Yahoo adapter

    def download(self, symbol: str, interval: str = "5m", days: int = 90) -> pd.DataFrame:
        """
        Download OHLCV data from OpenAlgo API for MCX commodities.

        Args:
            symbol: MCX symbol (e.g. GOLDM05FEB26FUT)
            interval: 5m, 15m, 1h (OpenAlgo intervals)
            days: Number of days of history to fetch (default 90 for commodities)

        Returns:
            DataFrame with columns: datetime, open, high, low, close, volume
        """
        # Check cache
        cache_key = f"{symbol}_{interval}_{days}"
        if cache_key in self.cache:
            cache_time, cached_df = self.cache[cache_key]
            if time.time() - cache_time < self.cache_ttl:
                logger.debug(f"Using cached data for {symbol} ({interval})")
                return cached_df.copy()

        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days)

        # Format dates for OpenAlgo API
        start_date = start_dt.strftime("%Y-%m-%d")
        end_date = end_dt.strftime("%Y-%m-%d")

        logger.info(f"Downloading {symbol} ({interval}) from OpenAlgo MCX...")

        try:
            # OpenAlgo historical data endpoint
            url = f"{OPENALGO_BASE_URL}/history/"

            payload = {
                "apikey": self.api_key,
                "symbol": symbol,
                "exchange": self.exchange,
                "interval": interval,
                "start_date": start_date,
                "end_date": end_date
            }

            response = requests.post(url, json=payload, timeout=30.0)

            if response.status_code == 400:
                logger.warning(f"Symbol {symbol} not found on MCX or invalid parameters.")
                return None

            if response.status_code == 403:
                logger.error("API key invalid or insufficient permissions.")
                return None

            if response.status_code == 429:
                logger.warning("Rate limited by OpenAlgo.")
                time.sleep(2)
                return None

            response.raise_for_status()

            data = response.json()

            if data.get("status") != "success":
                logger.warning(f"API returned error: {data.get('message', 'Unknown error')}")
                return None

            # Extract data from response
            if "data" not in data or not data["data"]:
                logger.warning(f"Empty data for {symbol}")
                return None

            # Convert to DataFrame
            # OpenAlgo returns list of dicts with timestamp, open, high, low, close, volume
            df = pd.DataFrame(data["data"])

            if df.empty:
                logger.warning(f"Empty DataFrame for {symbol}")
                return None

            # Standardize columns
            df.columns = [c.lower() for c in df.columns]

            # Rename timestamp to datetime if needed
            if 'timestamp' in df.columns:
                df.rename(columns={'timestamp': 'datetime'}, inplace=True)
            elif 'time' in df.columns:
                df.rename(columns={'time': 'datetime'}, inplace=True)

            # Parse datetime
            # OpenAlgo typically returns ISO format or unix timestamp
            if df['datetime'].dtype == 'int64':
                # Unix timestamp
                df['datetime'] = pd.to_datetime(df['datetime'], unit='s', utc=True)
            else:
                # ISO string
                df['datetime'] = pd.to_datetime(df['datetime'], utc=True)

            # Convert to IST (UTC+5:30)
            df['datetime'] = df['datetime'].dt.tz_convert('Asia/Kolkata')

            # Drop null values
            df.dropna(inplace=True)

            # Ensure numeric columns
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # Final cleanup
            df.dropna(inplace=True)

            # Validate data quality
            if not self._validate_ohlc(df):
                logger.warning(f"Invalid OHLC data for {symbol}")
                return None

            # Sort by datetime
            df.sort_values('datetime', inplace=True)
            df.reset_index(drop=True, inplace=True)

            if df.empty:
                logger.warning(f"No valid data after processing for {symbol}")
                return None

            # Cache the result
            self.cache[cache_key] = (time.time(), df.copy())

            logger.info(f"Downloaded {len(df)} bars for {symbol} ({interval})")
            return df

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error downloading {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to download {symbol}: {e}")
            return None

    def _validate_ohlc(self, df: pd.DataFrame) -> bool:
        """
        Validate OHLC data quality.

        Returns:
            True if data is valid, False otherwise
        """
        if df.empty:
            return False

        # Check required columns exist
        required_cols = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            return False

        # Check OHLC relationships (high >= low, high >= open/close, low <= open/close)
        invalid_bars = (
            (df['high'] < df['low']) |
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close'])
        ).sum()

        if invalid_bars > len(df) * 0.01:  # Allow 1% error tolerance
            logger.warning(f"Invalid OHLC bars: {invalid_bars}/{len(df)} ({invalid_bars/len(df)*100:.1f}%)")
            return False

        # Check for negative prices
        if (df[['open', 'high', 'low', 'close']] <= 0).any().any():
            logger.warning("Negative or zero prices detected")
            return False

        # Check for negative volume
        if (df['volume'] < 0).any():
            logger.warning("Negative volume detected")
            return False

        return True

    def clear_cache(self):
        """Clear the data cache."""
        self.cache = {}
        logger.info("MCX data cache cleared")
