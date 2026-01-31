import pandas as pd
import logging
from datetime import datetime, timedelta
import os
import re

logger = logging.getLogger("SymbolResolver")

class SymbolResolver:
    def __init__(self, instruments_path=None):
        if instruments_path is None:
            # Default to openalgo/data/instruments.csv
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

                # Normalize columns
                if 'instrument_type' not in self.df.columns and 'segment' in self.df.columns:
                     # Map segment to instrument_type if missing (fallback)
                     self.df['instrument_type'] = self.df['segment'].apply(lambda x: 'FUT' if 'FUT' in str(x) else ('OPT' if 'OPT' in str(x) else 'EQ'))

                logger.info(f"Loaded {len(self.df)} instruments from {self.instruments_path}")
            except Exception as e:
                logger.error(f"Failed to load instruments: {e}")
        else:
            logger.warning(f"Instruments file not found at {self.instruments_path}")

    def resolve(self, config):
        """
        Resolve a strategy config to a tradable symbol or list of candidates.
        Used primarily for validation during Daily Prep.
        """
        itype = config.get('type', 'EQUITY').upper()
        underlying = config.get('underlying')
        if not underlying:
            underlying = config.get('symbol')

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

    def get_tradable_symbol(self, config, spot_price=None):
        """
        Get a specific tradable symbol for execution.
        For Options, requires spot_price to determine Strike if 'ATM/ITM/OTM' is used.
        """
        itype = config.get('type', 'EQUITY').upper()

        if itype == 'OPT':
            return self._get_option_symbol(config, spot_price)
        else:
            # For Equity/Futures, resolve returns the specific symbol
            return self.resolve(config)

    def _resolve_equity(self, symbol, exchange):
        if self.df.empty: return symbol

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
        if self.df.empty: return f"{underlying}FUT"

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # Filter for Futures of this underlying
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'FUT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        matches = self.df[mask].sort_values('expiry')

        if matches.empty:
            # Try searching by symbol if name match fails
            mask_sym = (self.df['symbol'].str.startswith(underlying)) & \
                       (self.df['instrument_type'] == 'FUT') & \
                       (self.df['exchange'] == exchange) & \
                       (self.df['expiry'] >= now)
            matches = self.df[mask_sym].sort_values('expiry')

            if matches.empty:
                logger.warning(f"No futures found for {underlying}")
                return None

        # MCX MINI Logic
        if exchange == 'MCX':
            # Priority:
            # 1. Symbol contains 'MINI'
            # 2. Symbol matches Name + 'M' + Date (e.g., SILVERM...) vs SILVER...

            # Check for explicitly 'MINI' or 'M' suffix on underlying name
            # Use non-capturing group to avoid pandas UserWarning
            mini_pattern = r'(?:{}M|{}MINI)'.format(underlying, underlying)

            mini_matches = matches[matches['symbol'].str.contains(mini_pattern, regex=True, flags=re.IGNORECASE)]

            if not mini_matches.empty:
                logger.info(f"Found MCX MINI contract for {underlying}: {mini_matches.iloc[0]['symbol']}")
                return mini_matches.iloc[0]['symbol']

            # Also check if the symbol itself ends with 'M' before some digits (less reliable but possible)
            # e.g. CRUDEOILM23NOV...

            logger.info(f"No MCX MINI contract found for {underlying}, falling back to standard.")

        # Return nearest expiry
        return matches.iloc[0]['symbol']

    def _resolve_option(self, config):
        underlying = config.get('underlying')
        option_type = config.get('option_type', 'CE').upper()
        expiry_pref = config.get('expiry_preference', 'WEEKLY').upper()
        exchange = config.get('exchange', 'NFO')

        if self.df.empty: return None

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        # Pre-filter by Option Type if possible (though we might need both for straddles, here we resolve for specific type)
        if option_type:
             mask &= self.df['symbol'].str.endswith(option_type)

        matches = self.df[mask].copy()

        if matches.empty:
            # Try name mapping (e.g. NIFTY 50 -> NIFTY)
            if underlying == 'NIFTY 50':
                return self._resolve_option({**config, 'underlying': 'NIFTY'})
            if underlying == 'NIFTY BANK':
                return self._resolve_option({**config, 'underlying': 'BANKNIFTY'})

            logger.warning(f"No options found for {underlying} {option_type}")
            return None

        # Expiry Selection
        unique_expiries = sorted(matches['expiry'].unique())
        if not unique_expiries:
            return None

        selected_expiry = self._select_expiry(unique_expiries, expiry_pref)

        # Filter for this expiry
        matches = matches[matches['expiry'] == selected_expiry]

        if matches.empty:
            return None

        return {
            'status': 'valid',
            'expiry': selected_expiry.strftime('%Y-%m-%d'),
            'sample_symbol': matches.iloc[0]['symbol'],
            'count': len(matches)
        }

    def _select_expiry(self, unique_expiries, expiry_pref):
        if not unique_expiries: return None

        # 1. Identify the nearest expiry (base reference)
        nearest_expiry = unique_expiries[0]

        if expiry_pref == 'WEEKLY':
            return nearest_expiry

        elif expiry_pref == 'MONTHLY':
            # Logic: Select the last expiry of the *current month cycle*.
            # If nearest_expiry is in Oct, find the last expiry in Oct.

            target_year = nearest_expiry.year
            target_month = nearest_expiry.month

            same_month_expiries = [
                d for d in unique_expiries
                if d.year == target_year and d.month == target_month
            ]

            if same_month_expiries:
                return same_month_expiries[-1]
            else:
                return nearest_expiry

        return nearest_expiry

    def _get_option_symbol(self, config, spot_price):
        """
        Find specific option symbol based on spot price and strike criteria (ATM, ITM, OTM).
        """
        if spot_price is None:
            logger.error("Spot price required to resolve Option Symbol")
            return None

        valid_set = self._resolve_option(config)
        if not valid_set or valid_set.get('status') != 'valid':
            return None

        expiry_date = pd.to_datetime(valid_set['expiry'])
        underlying = config.get('underlying')
        exchange = config.get('exchange', 'NFO')
        option_type = config.get('option_type', 'CE').upper()
        strike_criteria = config.get('strike_criteria', 'ATM').upper() # ATM, ITM, OTM

        # Filter instruments for this specific expiry
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] == expiry_date) & \
               (self.df['symbol'].str.endswith(option_type))

        chain = self.df[mask].copy()

        if chain.empty:
            return None

        # Extract Strike Price
        # Assuming symbol format or having a 'strike' column.
        # If 'strike' column doesn't exist, we must parse symbol or assume 'strike' exists in master.
        # OpenAlgo/Kite master usually has 'strike'.

        if 'strike' not in chain.columns:
            # Try to parse strike from symbol (e.g. NIFTY23OCT19500CE)
            # This is brittle but a fallback.
            # Regex: look for digits before CE/PE
            def parse_strike(sym):
                m = re.search(r'(\d+)(CE|PE)$', sym)
                return float(m.group(1)) if m else 0
            chain['strike'] = chain['symbol'].apply(parse_strike)

        # Sort by strike
        chain = chain.sort_values('strike')

        # Find ATM Strike
        # Simple logic: closest to spot
        chain['diff'] = abs(chain['strike'] - spot_price)
        atm_row = chain.loc[chain['diff'].idxmin()]
        atm_strike = atm_row['strike']

        selected_strike = atm_strike

        # Adjust for ITM/OTM (Simple 1-step logic, can be enhanced)
        strikes = sorted(chain['strike'].unique())
        atm_index = strikes.index(atm_strike)

        if strike_criteria == 'ITM':
            # Call ITM = Lower Strike, Put ITM = Higher Strike
            if option_type == 'CE':
                idx = max(0, atm_index - 1)
            else:
                idx = min(len(strikes)-1, atm_index + 1)
            selected_strike = strikes[idx]

        elif strike_criteria == 'OTM':
            # Call OTM = Higher Strike, Put OTM = Lower Strike
            if option_type == 'CE':
                idx = min(len(strikes)-1, atm_index + 1)
            else:
                idx = max(0, atm_index - 1)
            selected_strike = strikes[idx]

        # Get final symbol
        final_row = chain[chain['strike'] == selected_strike]
        if not final_row.empty:
            return final_row.iloc[0]['symbol']

        return atm_row['symbol']
