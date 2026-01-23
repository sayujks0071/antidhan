"""Instrument synchronization and universe management"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

import pandas as pd
import structlog
from kiteconnect import KiteConnect

from packages.core.config import Settings, UniverseConfig
from packages.core.models import Instrument, InstrumentType

logger = structlog.get_logger(__name__)


class InstrumentManager:
    """Manages instrument data and universe"""
    
    def __init__(self, kite: KiteConnect, config: UniverseConfig, settings: Settings):
        self.kite = kite
        self.config = config
        self.settings = settings
        
        # Cache
        self._instruments: Dict[int, Instrument] = {}
        self._symbols_to_tokens: Dict[str, int] = {}
        self._universe_tokens: Set[int] = set()
        self._fo_ban_list: Set[str] = set()
        
        # Metadata
        self.last_sync: Optional[datetime] = None
        
    async def sync_instruments(self) -> bool:
        """
        Synchronize instrument data from Kite Connect.
        Fetches all instruments and caches them locally.
        """
        try:
            logger.info("Starting instrument synchronization")
            
            # Fetch instruments from all relevant exchanges
            exchanges = ["NSE", "NFO", "BSE", "BFO", "MCX"]
            all_instruments = []
            
            for exchange in exchanges:
                try:
                    instruments = self.kite.instruments(exchange)
                    all_instruments.extend(instruments)
                    logger.info(f"Fetched {len(instruments)} instruments from {exchange}")
                except Exception as e:
                    logger.error(f"Failed to fetch instruments from {exchange}: {e}")
            
            # Parse and cache instruments
            self._parse_instruments(all_instruments)
            
            self.last_sync = datetime.now()
            logger.info(f"Instrument sync complete. Total instruments: {len(self._instruments)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Instrument sync failed: {e}")
            return False
    
    def _parse_instruments(self, raw_instruments: List[Dict]) -> None:
        """Parse raw instrument data into Instrument objects"""
        self._instruments.clear()
        self._symbols_to_tokens.clear()
        
        for raw in raw_instruments:
            try:
                # Determine instrument type
                inst_type = self._map_instrument_type(raw.get("instrument_type", "EQ"))
                
                # Parse expiry
                expiry = None
                if raw.get("expiry"):
                    expiry = pd.to_datetime(raw["expiry"])
                
                # Create Instrument
                instrument = Instrument(
                    token=raw["instrument_token"],
                    symbol=raw["name"],
                    tradingsymbol=raw["tradingsymbol"],
                    exchange=raw["exchange"],
                    instrument_type=inst_type,
                    expiry=expiry,
                    strike=raw.get("strike"),
                    lot_size=raw.get("lot_size", 1),
                    tick_size=raw.get("tick_size", 0.05),
                    freeze_quantity=raw.get("freeze_quantity"),
                    segment=raw.get("segment"),
                    isin=raw.get("isin")
                )
                
                self._instruments[instrument.token] = instrument
                self._symbols_to_tokens[instrument.tradingsymbol] = instrument.token
                
            except Exception as e:
                logger.warning(f"Failed to parse instrument: {raw.get('tradingsymbol', 'unknown')} - {e}")
    
    def _map_instrument_type(self, raw_type: str) -> InstrumentType:
        """Map raw instrument type to InstrumentType enum"""
        mapping = {
            "EQ": InstrumentType.EQ,
            "FUT": InstrumentType.FUT,
            "CE": InstrumentType.CE,
            "PE": InstrumentType.PE,
        }
        return mapping.get(raw_type, InstrumentType.EQ)
    
    async def sync_fo_ban_list(self) -> None:
        """
        Synchronize F&O ban list from NSE.
        This list contains stocks currently under F&O ban due to high positions.
        """
        try:
            # In production, fetch from NSE website or Kite's margin API
            # For now, we'll maintain an empty list and update it manually
            # NSE publishes this daily at: https://www.nseindia.com/api/fo-ban-securities
            
            logger.info("Syncing F&O ban list")
            
            # Placeholder: In production, implement actual fetching logic
            # Example banned stocks (for demo purposes):
            # self._fo_ban_list = {"DELTACORP", "GNFC", "MANAPPURAM"}
            
            self._fo_ban_list.clear()
            logger.info(f"F&O ban list synced. {len(self._fo_ban_list)} symbols banned")
            
        except Exception as e:
            logger.error(f"Failed to sync F&O ban list: {e}")
    
    def is_fo_banned(self, symbol: str) -> bool:
        """Check if a symbol is currently under F&O ban"""
        return symbol in self._fo_ban_list
    
    async def build_universe(self) -> List[int]:
        """
        Build trading universe based on configuration.
        Returns list of instrument tokens to subscribe to.
        """
        try:
            logger.info("Building trading universe")
            
            universe_tokens = set()
            
            # 1. Add index futures
            for index_name in self.config.indices:
                tokens = self._get_index_instruments(index_name)
                universe_tokens.update(tokens)
                logger.info(f"Added {len(tokens)} instruments for {index_name}")
            
            # 2. Add liquid F&O stocks
            if self.config.fo_stocks_liquidity_rank_top_n > 0:
                fo_tokens = await self._get_liquid_fo_stocks(
                    self.config.fo_stocks_liquidity_rank_top_n
                )
                universe_tokens.update(fo_tokens)
                logger.info(f"Added {len(fo_tokens)} liquid F&O stocks")
            
            self._universe_tokens = universe_tokens
            logger.info(f"Universe built with {len(universe_tokens)} instruments")
            
            return list(universe_tokens)
            
        except Exception as e:
            logger.error(f"Failed to build universe: {e}")
            return []
    
    def _get_index_instruments(self, index_name: str) -> Set[int]:
        """Get instruments for a specific index"""
        tokens = set()
        
        # Map index names to tradingsymbols
        index_map = {
            "NIFTY": "NIFTY",
            "BANKNIFTY": "BANKNIFTY",
            "FINNIFTY": "FINNIFTY",
            "SENSEX": "SENSEX",
            "BANKEX": "BANKEX"
        }
        
        base_symbol = index_map.get(index_name)
        if not base_symbol:
            logger.warning(f"Unknown index: {index_name}")
            return tokens
        
        # Determine exchange based on index
        spot_exchange = "BSE" if index_name in ["SENSEX", "BANKEX"] else "NSE"
        deriv_exchange = "BFO" if index_name in ["SENSEX", "BANKEX"] else "NFO"

        # Get spot index token
        for token, inst in self._instruments.items():
            if inst.symbol == base_symbol and inst.exchange == spot_exchange and inst.instrument_type == InstrumentType.EQ:
                tokens.add(token)
                break
        
        # Get current month and next month futures
        now = datetime.now()
        
        for token, inst in self._instruments.items():
            if inst.symbol == base_symbol and inst.exchange == deriv_exchange:
                if inst.is_future and inst.expiry:
                    # Include futures expiring within next 60 days
                    if inst.expiry <= now + timedelta(days=60):
                        tokens.add(token)
        
        return tokens
    
    async def _get_liquid_fo_stocks(self, top_n: int) -> Set[int]:
        """
        Get most liquid F&O stocks.
        Filters by turnover, excludes banned stocks.
        """
        tokens = set()
        
        try:
            # Get all unique F&O stock symbols
            fo_stocks = set()
            for token, inst in self._instruments.items():
                if inst.exchange == "NFO" and inst.symbol not in ["NIFTY", "BANKNIFTY", "FINNIFTY"]:
                    fo_stocks.add(inst.symbol)
            
            # Exclude F&O banned stocks
            if self.config.exclude_fo_ban:
                fo_stocks = {s for s in fo_stocks if not self.is_fo_banned(s)}
            
            # In production, fetch turnover data and rank
            # For now, select first top_n stocks alphabetically (placeholder)
            selected_stocks = sorted(list(fo_stocks))[:top_n]
            
            # Get current month futures for selected stocks
            now = datetime.now()
            for symbol in selected_stocks:
                for token, inst in self._instruments.items():
                    if inst.symbol == symbol and inst.exchange == "NFO" and inst.is_future:
                        if inst.expiry and inst.expiry <= now + timedelta(days=30):
                            tokens.add(token)
                            break
            
            logger.info(f"Selected {len(selected_stocks)} liquid F&O stocks")
            
        except Exception as e:
            logger.error(f"Failed to get liquid F&O stocks: {e}")
        
        return tokens
    
    def get_instrument(self, token: int) -> Optional[Instrument]:
        """Get instrument by token"""
        return self._instruments.get(token)
    
    def get_instrument_by_symbol(self, tradingsymbol: str) -> Optional[Instrument]:
        """Get instrument by trading symbol"""
        token = self._symbols_to_tokens.get(tradingsymbol)
        if token:
            return self._instruments.get(token)
        return None
    
    def get_universe_tokens(self) -> List[int]:
        """Get current universe tokens"""
        return list(self._universe_tokens)
    
    def get_options_chain(
        self,
        symbol: str,
        expiry: Optional[datetime] = None,
        strikes_from_atm: int = 5
    ) -> List[Instrument]:
        """
        Get options chain for a symbol.
        
        Args:
            symbol: Underlying symbol (e.g., "NIFTY", "BANKNIFTY")
            expiry: Specific expiry date (None for nearest)
            strikes_from_atm: Number of strikes above and below ATM to include
        
        Returns:
            List of option instruments
        """
        options = []
        
        # Find all options for this symbol
        symbol_options = [
            inst for inst in self._instruments.values()
            if inst.symbol == symbol and inst.is_option and inst.exchange == "NFO"
        ]
        
        if not symbol_options:
            return options
        
        # Filter by expiry
        if expiry is None:
            # Get nearest expiry
            expiries = sorted([opt.expiry for opt in symbol_options if opt.expiry])
            if expiries:
                expiry = expiries[0]
        
        if expiry:
            symbol_options = [opt for opt in symbol_options if opt.expiry == expiry]
        
        # Get ATM strike (would need current spot price in production)
        # For now, get middle strikes
        strikes = sorted(set([opt.strike for opt in symbol_options if opt.strike]))
        if len(strikes) > 2 * strikes_from_atm:
            mid_idx = len(strikes) // 2
            selected_strikes = strikes[mid_idx - strikes_from_atm: mid_idx + strikes_from_atm + 1]
        else:
            selected_strikes = strikes
        
        # Filter by strikes
        options = [
            opt for opt in symbol_options
            if opt.strike in selected_strikes
        ]
        
        return options
    
    def get_nearest_expiry(self, symbol: str) -> Optional[datetime]:
        """Get nearest expiry date for a symbol"""
        expiries = []
        
        for inst in self._instruments.values():
            if inst.symbol == symbol and inst.expiry and inst.exchange == "NFO":
                expiries.append(inst.expiry)
        
        if expiries:
            return min(expiries)
        
        return None
    
    def filter_options_by_liquidity(
        self,
        options: List[Instrument],
        min_oi: int = 20000,
        max_spread_pct: float = 0.5
    ) -> List[Instrument]:
        """
        Filter options by liquidity criteria.
        
        Note: OI and spread require live market data.
        This is a placeholder that returns all options.
        In production, fetch market data and filter accordingly.
        """
        # In production:
        # 1. Fetch quotes for all option tokens
        # 2. Filter by OI >= min_oi
        # 3. Filter by bid-ask spread <= max_spread_pct of mid
        
        return options
