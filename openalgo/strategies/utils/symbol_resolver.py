import pandas as pd
import logging
from datetime import datetime, timedelta
import os

logger = logging.getLogger("SymbolResolver")

class SymbolResolver:
    def __init__(self, instruments_path=None):
        if instruments_path is None:
            # Default to openalgo/data/instruments.csv
            # __file__ = openalgo/strategies/utils/symbol_resolver.py
            # Go up two levels to 'openalgo' and then into 'data'
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data'))
            instruments_path = os.path.join(base_path, 'instruments.csv')

        self.instruments_path = instruments_path
        self.df = pd.DataFrame()
        self.load_instruments()

    def load_instruments(self):
        if os.path.exists(self.instruments_path):
            try:
                self.df = pd.read_csv(self.instruments_path)
                # Ensure expiry is datetime
                if 'expiry' in self.df.columns:
                    self.df['expiry'] = pd.to_datetime(self.df['expiry'], errors='coerce')
                logger.info(f"Loaded {len(self.df)} instruments from {self.instruments_path}")
            except Exception as e:
                logger.error(f"Failed to load instruments: {e}")
        else:
            logger.warning(f"Instruments file not found at {self.instruments_path}")

    def resolve(self, config):
        """
        Resolve a strategy config to a tradable symbol or list of candidates.
        config: dict with keys 'underlying', 'type', 'exchange', etc.
        """
        itype = config.get('type', 'EQUITY').upper()
        underlying = config.get('underlying')
        exchange = config.get('exchange', 'NSE')

        if itype == 'EQUITY':
            return self._resolve_equity(underlying, exchange)
        elif itype == 'FUT':
            return self._resolve_future(underlying, exchange)
        elif itype == 'OPT':
            return self._resolve_option(config)
        else:
            logger.error(f"Unknown instrument type: {itype}")
            return None

    def _resolve_equity(self, symbol, exchange):
        if self.df.empty: return symbol # Fallback

        # Simple existence check
        mask = (self.df['name'] == symbol) & (self.df['instrument_type'] == 'EQ') & (self.df['exchange'] == exchange)
        matches = self.df[mask]

        if not matches.empty:
            return matches.iloc[0]['symbol']

        # Try direct symbol match
        mask = (self.df['symbol'] == symbol) & (self.df['exchange'] == exchange)
        matches = self.df[mask]
        if not matches.empty:
            return matches.iloc[0]['symbol']

        logger.warning(f"Equity {symbol} not found in master list")
        return symbol

    def _resolve_future(self, underlying, exchange):
        if self.df.empty: return f"{underlying}FUT" # Fallback

        now = datetime.now()
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'FUT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        matches = self.df[mask].sort_values('expiry')

        if matches.empty:
            logger.warning(f"No futures found for {underlying}")
            return None

        # MCX MINI Logic
        if exchange == 'MCX':
            # Try to find MINI contracts
            mini_matches = matches[matches['symbol'].str.contains('M', na=False) | matches['symbol'].str.contains('MINI', na=False)]
            # Note: MCX symbols often like SILVERM or SILVERMIC.
            # If MINI preferred and found:
            if not mini_matches.empty:
                logger.info(f"Found MCX MINI contract for {underlying}: {mini_matches.iloc[0]['symbol']}")
                return mini_matches.iloc[0]['symbol']
            else:
                logger.info(f"No MCX MINI contract found for {underlying}, falling back to standard.")

        # Return nearest expiry
        return matches.iloc[0]['symbol']

    def _resolve_option(self, config):
        underlying = config.get('underlying')
        option_type = config.get('option_type', 'CE').upper() # CE or PE
        expiry_pref = config.get('expiry_preference', 'WEEKLY').upper() # WEEKLY or MONTHLY
        exchange = config.get('exchange', 'NFO')

        if self.df.empty: return f"{underlying}OPT"

        now = datetime.now()
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        if option_type:
             # Assuming symbol ends with CE/PE or instrument_type distinguishes?
             # Standard CSV usually has 'instrument_type' as 'OPTIDX' or 'OPTSTK'.
             # And symbol like NIFTY23OCT19500CE.
             mask &= self.df['symbol'].str.endswith(option_type)

        matches = self.df[mask].copy()

        if matches.empty:
            logger.warning(f"No options found for {underlying} {option_type}")
            return None

        # Expiry Selection
        unique_expiries = sorted(matches['expiry'].unique())
        if not unique_expiries:
            return None

        selected_expiry = None

        if expiry_pref == 'WEEKLY':
            # Nearest expiry is usually the weekly one
            selected_expiry = unique_expiries[0]
        elif expiry_pref == 'MONTHLY':
            # Logic: Monthly expiry is typically the last Thursday of the month.
            # We assume the monthly contract is the last expiry available in the current month cycle.

            # 1. Identify the month of the nearest available expiry
            nearest_expiry = unique_expiries[0]

            # 2. Find all expiries falling in that same month
            same_month_expiries = [
                d for d in unique_expiries
                if d.year == nearest_expiry.year and d.month == nearest_expiry.month
            ]

            # 3. Select the last one (The Monthly contract)
            if same_month_expiries:
                selected_expiry = same_month_expiries[-1]
            else:
                # Should not happen given logic, fallback
                selected_expiry = nearest_expiry
        else:
            selected_expiry = unique_expiries[0]

        matches = matches[matches['expiry'] == selected_expiry]

        # Strike Selection (if provided specific strike, usually not available in config, but derived dynamically)
        # The resolver here validates we have *contracts* for this expiry.
        # It returns the *expiry date* and *symbol prefix* or just a validation success.

        # If the strategy needs a specific symbol (e.g. ATM), it needs Spot price.
        # This resolver is static.
        # We can return a template or just the first match to prove existence.

        return {
            'status': 'valid',
            'expiry': selected_expiry.strftime('%Y-%m-%d'),
            'sample_symbol': matches.iloc[0]['symbol'],
            'count': len(matches)
        }
