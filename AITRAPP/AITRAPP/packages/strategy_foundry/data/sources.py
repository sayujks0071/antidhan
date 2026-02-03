import logging
from datetime import datetime, timedelta
from io import StringIO

import pandas as pd
import requests

logger = logging.getLogger(__name__)

YAHOO_URL = "https://query1.finance.yahoo.com/v7/finance/download/{symbol}?period1={start}&period2={end}&interval={interval}&events=history&includeAdjustedClose=true"

class YahooSource:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
        }

    def download(self, symbol: str, interval: str = "1d", days: int = 365) -> pd.DataFrame:
        """
        Download OHLCV data from Yahoo Finance.

        Args:
            symbol: Ticker symbol (e.g. ^NSEI)
            interval: 1d, 5m, 15m
            days: Number of days of history to fetch
        """
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days)

        # Yahoo expects unix timestamp
        period1 = int(start_dt.timestamp())
        period2 = int(end_dt.timestamp())

        url = YAHOO_URL.format(symbol=symbol, start=period1, end=period2, interval=interval)

        logger.info(f"Downloading {symbol} ({interval}) from Yahoo...")

        try:
            response = requests.get(url, headers=self.headers, timeout=10.0)

            if response.status_code == 404:
                logger.warning(f"Symbol {symbol} not found on Yahoo.")
                return None

            if response.status_code == 429:
                logger.warning("Rate limited by Yahoo.")
                return None

            response.raise_for_status()

            if not response.text:
                logger.warning(f"Empty response for {symbol}")
                return None

            df = pd.read_csv(StringIO(response.text))

            # Standardize columns
            df.columns = [c.lower() for c in df.columns]
            if 'date' in df.columns:
                df.rename(columns={'date': 'datetime'}, inplace=True)

            # Parse datetime
            # Yahoo daily is YYYY-MM-DD, intraday is YYYY-MM-DD HH:MM:SS-Offset
            # We want tz-aware (UTC) then convert to IST?
            # Actually Yahoo usually returns UTC for intraday.

            df['datetime'] = pd.to_datetime(df['datetime'], utc=True)

            # Convert to IST
            # We will handle timezone conversion in Loader to be consistent

            df.dropna(inplace=True)

            # Ensure float columns
            cols = ['open', 'high', 'low', 'close', 'adj close', 'volume']
            for c in cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')

            df.dropna(inplace=True)

            if df.empty:
                return None

            return df

        except Exception as e:
            logger.error(f"Failed to download {symbol}: {e}")
            return None
