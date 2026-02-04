"""Historical data loader for NSE options CSV files"""
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import structlog

from packages.core.models import Bar, Tick

logger = structlog.get_logger(__name__)


class HistoricalDataLoader:
    """
    Loads historical options data from NSE CSV files.
    
    Expected CSV format:
    Symbol, Date, Expiry, Option type, Strike Price, Open, High, Low, Close,
    LTP, Settle Price, No. of contracts, Turnover, Premium Turnover,
    Open Int, Change in OI, Underlying Value
    """

    def __init__(self, data_dir: str = "docs/NSE OPINONS DATA"):
        self.data_dir = Path(data_dir)
        self._cache: Dict[str, pd.DataFrame] = {}

        # Fallback to fixtures if configured dir doesn't exist
        if not self.data_dir.exists():
            fixtures_path = Path("tests/fixtures")
            if fixtures_path.exists():
                logger.warning(f"Data dir {self.data_dir} not found, falling back to {fixtures_path}")
                self.data_dir = fixtures_path

    def _validate_input(self, text: str):
        """Validate input to prevent path traversal"""
        if not re.match(r"^[a-zA-Z0-9_-]+$", text):
            raise ValueError(f"Invalid input: {text}. Only alphanumeric, underscore, and hyphen allowed.")

    def validate_data(self, df: pd.DataFrame, filename: str) -> pd.DataFrame:
        """
        Validate data quality and filter invalid records.

        Checks:
        1. Positive prices (Open, High, Low, Close)
        2. OHLC consistency (High >= Low, High >= Open, High >= Close, Low <= Open, Low <= Close)
        3. Non-negative volume and OI
        """
        if df.empty:
            return df

        initial_len = len(df)

        # 1. Positive Prices
        price_cols = ['Open', 'High', 'Low', 'Close']
        for col in price_cols:
            if col in df.columns:
                df = df[df[col] > 0]

        # 2. OHLC Consistency
        if all(col in df.columns for col in price_cols):
            mask = (
                (df['High'] >= df['Low']) &
                (df['High'] >= df['Open']) &
                (df['High'] >= df['Close']) &
                (df['Low'] <= df['Open']) &
                (df['Low'] <= df['Close'])
            )
            df = df[mask]

        # 3. Non-negative Volume/OI
        if 'No. of contracts' in df.columns:
            # Handle NaNs in Volume
            df = df[ (df['No. of contracts'].isna()) | (df['No. of contracts'] >= 0) ]

        if 'Open Int' in df.columns:
             # Handle NaNs in OI before checking
             df = df[ (df['Open Int'].isna()) | (df['Open Int'] >= 0) ]

        if len(df) < initial_len:
            logger.warning(
                f"Dropped {initial_len - len(df)} invalid records from {filename} (remaining: {len(df)})"
            )

        return df

    def load_file(
        self,
        symbol: str,
        option_type: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Load historical data from CSV file.
        
        Args:
            symbol: NIFTY or BANKNIFTY
            option_type: CE or PE
            start_date: Filter start date (optional)
            end_date: Filter end date (optional)
        
        Returns:
            DataFrame with historical data
        """
        self._validate_input(symbol)
        self._validate_input(option_type)
        # Input validation for security (path traversal prevention)
        if not re.match(r"^[a-zA-Z0-9_-]+$", symbol):
            raise ValueError(f"Invalid symbol format: {symbol}")

        if option_type not in ["CE", "PE"]:
            raise ValueError(f"Invalid option type: {option_type}")

        # Construct filename
        # Allow flexible filename matching in future, but stick to pattern for now
        filename = f"OPTIDX_{symbol}_{option_type}_12-Aug-2025_TO_12-Nov-2025.csv"
        filepath = self.data_dir / filename

        if not filepath.exists():
            # Try finding any matching file if exact match fails
            pattern = f"OPTIDX_{symbol}_{option_type}*.csv"
            matches = list(self.data_dir.glob(pattern))
            if matches:
                filepath = matches[0]
                logger.info(f"Exact match not found, using {filepath.name}")
            else:
                raise FileNotFoundError(f"Historical data file not found: {filepath}")

        # Check cache
        cache_key = f"{filepath.name}"
        if cache_key in self._cache:
            df = self._cache[cache_key].copy()
        else:
            # Load CSV
            logger.info(f"Loading historical data from {filepath.name}")

            # First read without parsing dates to inspect columns
            df_preview = pd.read_csv(filepath, nrows=0, skipinitialspace=True)
            columns = [c.strip() for c in df_preview.columns]

            # Map common variations
            date_col = next((c for c in columns if c.lower() == 'date'), 'Date')
            expiry_col = next((c for c in columns if c.lower() == 'expiry'), 'Expiry')

            # Load full CSV
            df = pd.read_csv(
                filepath,
                skipinitialspace=True,
            )

            # Clean column names
            df.columns = df.columns.str.strip()

            # Handle date parsing manually to be more robust
            if date_col in df.columns:
                df['Date'] = pd.to_datetime(df[date_col], format='%d-%b-%Y', errors='coerce')
                # Fallback format if needed
                if df['Date'].isna().any():
                     df['Date'] = df['Date'].fillna(pd.to_datetime(df[date_col], errors='coerce'))

            if expiry_col in df.columns:
                df['Expiry'] = pd.to_datetime(df[expiry_col], format='%d-%b-%Y', errors='coerce')
                if df['Expiry'].isna().any():
                    df['Expiry'] = df['Expiry'].fillna(pd.to_datetime(df[expiry_col], errors='coerce'))

            # Convert numeric columns
            numeric_mapping = {
                'Strike Price': ['Strike Price', 'Strike'],
                'Open': ['Open'],
                'High': ['High'],
                'Low': ['Low'],
                'Close': ['Close'],
                'LTP': ['LTP', 'Last Price'],
                'Settle Price': ['Settle Price'],
                'No. of contracts': ['No. of contracts', 'Volume'],
                'Open Int': ['Open Int', 'OI'],
                'Underlying Value': ['Underlying Value', 'Spot']
            }

            for standard_name, variations in numeric_mapping.items():
                found_col = next((c for c in df.columns if c in variations), None)
                if found_col:
                    if found_col != standard_name:
                         df[standard_name] = df[found_col]
                    df[standard_name] = pd.to_numeric(df[standard_name], errors='coerce')

            # Drop rows with invalid dates
            df = df.dropna(subset=['Date'])

            # Validate Data
            df = self.validate_data(df, filepath.name)

            # Cache
            self._cache[cache_key] = df

        # Filter by date range
        if start_date:
            df = df[df['Date'] >= start_date]
        if end_date:
            df = df[df['Date'] <= end_date]

        # Sort by date
        df = df.sort_values('Date')

        logger.info(
            f"Loaded {len(df)} records for {symbol} {option_type}",
            date_range=(df['Date'].min(), df['Date'].max()) if len(df) > 0 else None
        )

        return df

    def get_options_chain(
        self,
        symbol: str,
        date: datetime,
        expiry: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Get options chain for a specific date.
        
        Args:
            symbol: NIFTY or BANKNIFTY
            date: Trading date
            expiry: Specific expiry (None for all)
        
        Returns:
            DataFrame with CE and PE options for the date
        """
        # Load both CE and PE
        ce_df = self.load_file(symbol, "CE")
        pe_df = self.load_file(symbol, "PE")

        # Filter by date
        ce_df = ce_df[ce_df['Date'] == date]
        pe_df = pe_df[pe_df['Date'] == date]

        # Filter by expiry if specified
        if expiry:
            ce_df = ce_df[ce_df['Expiry'] == expiry]
            pe_df = pe_df[pe_df['Expiry'] == expiry]

        # Combine
        ce_df['Option type'] = 'CE'
        pe_df['Option type'] = 'PE'

        chain = pd.concat([ce_df, pe_df], ignore_index=True)
        if not chain.empty:
            chain = chain.sort_values(['Strike Price', 'Option type'])

        return chain

    def get_strike_data(
        self,
        symbol: str,
        option_type: str,
        strike: float,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Get historical data for a specific strike.
        
        Args:
            symbol: NIFTY or BANKNIFTY
            option_type: CE or PE
            strike: Strike price
            start_date: Filter start date
            end_date: Filter end date
        
        Returns:
            DataFrame with time series for the strike
        """
        df = self.load_file(symbol, option_type, start_date, end_date)

        # Filter by strike
        df = df[df['Strike Price'] == strike]

        return df.sort_values('Date')

    def convert_to_bars(
        self,
        df: pd.DataFrame,
        symbol: str,
        strike: float,
        option_type: str
    ) -> List[Bar]:
        """
        Convert historical DataFrame to Bar objects.
        
        Args:
            df: Historical data DataFrame
            symbol: Underlying symbol
            strike: Strike price
            option_type: CE or PE
        
        Returns:
            List of Bar objects
        """
        if df.empty:
            return []

        # Extract columns as numpy arrays
        # Note: dates need to be converted to python datetime/timestamp for compatibility
        # Using list comprehension to avoid FutureWarning from .dt.to_pydatetime()
        dates = np.array([d.to_pydatetime() for d in df['Date']])
        opens = df['Open'].to_numpy()
        highs = df['High'].to_numpy()
        lows = df['Low'].to_numpy()
        closes = df['Close'].to_numpy()

        # Handle volume and OI with fallbacks
        if 'No. of contracts' in df.columns:
            volumes = df['No. of contracts'].fillna(0).astype(int).to_numpy()
        else:
            volumes = np.zeros(len(df), dtype=int)

        if 'Open Int' in df.columns:
            # Replace NaN with None safely
            ois = df['Open Int'].astype(object).where(pd.notna(df['Open Int']), None).to_numpy()
        else:
            ois = np.full(len(df), None)

        # Use list comprehension for faster object creation
        # token is 0 (set later)
        # Explicitly cast numpy types to python types (int, float) for JSON serialization safety
        return [
            Bar(
                token=0,
                timestamp=ts,
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=int(v),
                oi=int(oi) if oi is not None and not pd.isna(oi) else None
            )
            for ts, o, h, l, c, v, oi in zip(dates, opens, highs, lows, closes, volumes, ois)
        ]

    def convert_to_ticks(
        self,
        df: pd.DataFrame,
        symbol: str,
        strike: float,
        option_type: str
    ) -> List[Tick]:
        """
        Convert historical DataFrame to Tick objects.
        
        Uses LTP (Last Traded Price) as the tick price.
        
        Args:
            df: Historical data DataFrame
            symbol: Underlying symbol
            strike: Strike price
            option_type: CE or PE
        
        Returns:
            List of Tick objects
        """
        if df.empty:
            return []

        # Extract columns
        # Using list comprehension to avoid FutureWarning from .dt.to_pydatetime()
        dates = np.array([d.to_pydatetime() for d in df['Date']])
        opens = df['Open'].to_numpy()
        highs = df['High'].to_numpy()
        lows = df['Low'].to_numpy()
        closes = df['Close'].to_numpy()

        # LTP with fallback to Close
        if 'LTP' in df.columns:
            # Use where to handle NaNs in LTP
            ltps = df['LTP'].to_numpy()
            last_prices = np.where(pd.notna(ltps), ltps, closes)
        else:
            last_prices = closes

        # Volume
        if 'No. of contracts' in df.columns:
            volumes = df['No. of contracts'].fillna(0).astype(int).to_numpy()
        else:
            volumes = np.zeros(len(df), dtype=int)

        # OI
        if 'Open Int' in df.columns:
            ois = df['Open Int'].fillna(0).astype(int).to_numpy()
        else:
            ois = np.zeros(len(df), dtype=int)

        # Create ticks
        # Explicitly cast numpy types to python types (int, float) for JSON serialization safety
        return [
            Tick(
                token=0,
                timestamp=ts,
                last_price=float(lp),
                last_quantity=0,
                volume=int(v),
                bid=0.0,  # Historical data doesn't have bid/ask
                ask=0.0,
                bid_quantity=0,
                ask_quantity=0,
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                oi=int(oi),
                oi_day_high=0,
                oi_day_low=0
            )
            for ts, lp, v, o, h, l, c, oi in zip(dates, last_prices, volumes, opens, highs, lows, closes, ois)
        ]

    def get_atm_strikes(
        self,
        symbol: str,
        date: datetime,
        num_strikes: int = 5
    ) -> List[float]:
        """
        Get ATM (At-The-Money) strikes for a date.
        
        Args:
            symbol: NIFTY or BANKNIFTY
            date: Trading date
            num_strikes: Number of strikes above and below ATM
        
        Returns:
            List of strike prices around ATM
        """
        chain = self.get_options_chain(symbol, date)

        if chain.empty:
            return []

        # Get underlying value (spot)
        underlying_value = chain['Underlying Value'].iloc[0] if 'Underlying Value' in chain.columns else None

        if not underlying_value or pd.isna(underlying_value):
            # Estimate from strike prices if underlying is missing
            strikes = sorted(chain['Strike Price'].unique())
            if not strikes:
                return []
            underlying_value = strikes[len(strikes) // 2]

        # Find ATM strike (closest to underlying)
        strikes = sorted(chain['Strike Price'].unique())
        if not strikes:
            return []

        atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - underlying_value))

        # Get strikes around ATM
        start_idx = max(0, atm_idx - num_strikes)
        end_idx = min(len(strikes), atm_idx + num_strikes + 1)

        return strikes[start_idx:end_idx]

    def calculate_iv(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        date: datetime,
        expiry: datetime,
        risk_free_rate: float = 0.06
    ) -> Optional[float]:
        """
        Calculate implied volatility from historical data.
        """
        df = self.get_strike_data(symbol, option_type, strike)
        row = df[df['Date'] == date]

        if row.empty:
            return None

        row = row.iloc[0]
        spot = row['Underlying Value']
        premium = row['LTP'] if pd.notna(row['LTP']) else row['Close']
        time_to_expiry = (expiry - date).days / 365.0

        if time_to_expiry <= 0 or premium <= 0:
            return None

        # Simplified IV calculation (placeholder)
        iv_estimate = abs(premium / spot) / (time_to_expiry ** 0.5) * 2

        return min(max(iv_estimate, 0.05), 2.0)  # Clamp between 5% and 200%

    def get_date_range(self, symbol: str, option_type: str) -> tuple[datetime, datetime]:
        """Get available date range for a symbol/type"""
        df = self.load_file(symbol, option_type)

        if df.empty:
            return None, None

        return df['Date'].min(), df['Date'].max()

    def clear_cache(self):
        """Clear the data cache"""
        self._cache.clear()
        logger.info("Historical data cache cleared")
