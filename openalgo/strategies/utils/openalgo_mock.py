"""OpenAlgo API mock for backtesting using AITRAPP historical data"""
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

# Import AITRAPP modules
# Handle both relative and absolute imports
try:
    from .aitrapp_integration import HistoricalDataLoader, AITRAPP_PATH
except ImportError:
    # Absolute import fallback
    _utils_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _utils_dir)
    from aitrapp_integration import HistoricalDataLoader, AITRAPP_PATH

# Historical data directory
DATA_DIR = AITRAPP_PATH / "docs" / "NSE OPINONS DATA"

# Initialize data loader
_data_loader = None

def get_data_loader():
    """Get or create historical data loader"""
    global _data_loader
    if _data_loader is None:
        _data_loader = HistoricalDataLoader(str(DATA_DIR))
    return _data_loader


class OpenAlgoAPIMock:
    """Mock OpenAlgo API that uses historical data"""
    
    def __init__(self, current_timestamp: datetime):
        """
        Initialize mock API for a specific timestamp
        
        Args:
            current_timestamp: Current simulation timestamp
        """
        self.current_timestamp = current_timestamp
        self.data_loader = get_data_loader()
        self._cache: Dict[str, Any] = {}
        
    def post_json(self, path: str, payload: Dict) -> Dict:
        """
        Mock OpenAlgo API POST request
        
        Args:
            path: API endpoint path (e.g., "quotes", "optionchain")
            payload: Request payload
            
        Returns:
            Mock API response
        """
        path = path.rstrip('/').lower()
        
        if path == "quotes":
            return self._mock_quotes(payload)
        elif path == "optionchain":
            return self._mock_optionchain(payload)
        elif path == "optiongreeks":
            return self._mock_optiongreeks(payload)
        elif path == "history" or path == "history/":
            return self._mock_history(payload)
        elif path == "expiry":
            return self._mock_expiry(payload)
        elif path == "optionsymbol":
            return self._mock_optionsymbol(payload)
        else:
            return {"status": "error", "message": f"Unknown endpoint: {path}"}
    
    def _mock_quotes(self, payload: Dict) -> Dict:
        """Mock quotes endpoint"""
        symbol = payload.get("symbol", "")
        exchange = payload.get("exchange", "")
        
        # Parse symbol to extract underlying, strike, option type
        # Format: NIFTY25JAN202524500CE or NIFTY25000CE
        underlying, strike, option_type = self._parse_option_symbol(symbol)
        
        if not underlying:
            # Try as underlying index
            underlying = symbol
            strike = None
            option_type = None
        
        # Get data for current date
        date = self.current_timestamp.date()
        
        try:
            if option_type:
                # Option quote
                df = self.data_loader.get_strike_data(
                    underlying, option_type, strike,
                    start_date=datetime.combine(date, datetime.min.time()),
                    end_date=datetime.combine(date, datetime.max.time())
                )
                
                if df.empty:
                    return {"status": "error", "message": "No data found"}
                
                # Get latest row
                row = df.iloc[-1]
                
                return {
                    "status": "success",
                    "data": {
                        "symbol": symbol,
                        "exchange": exchange,
                        "ltp": float(row.get("LTP", row.get("Close", 0))),
                        "open": float(row.get("Open", 0)),
                        "high": float(row.get("High", 0)),
                        "low": float(row.get("Low", 0)),
                        "close": float(row.get("Close", 0)),
                        "volume": int(row.get("No. of contracts", 0)),
                        "oi": int(row.get("Open Int", 0)) if pd.notna(row.get("Open Int")) else 0,
                    }
                }
            else:
                # Underlying quote (simplified - use first option's underlying value)
                chain = self.data_loader.get_options_chain(underlying, datetime.combine(date, datetime.min.time()))
                if chain.empty:
                    return {"status": "error", "message": "No data found"}
                
                underlying_value = chain.iloc[0].get("Underlying Value", 0)
                return {
                    "status": "success",
                    "data": {
                        "symbol": symbol,
                        "exchange": exchange,
                        "ltp": float(underlying_value),
                        "open": float(underlying_value),
                        "high": float(underlying_value),
                        "low": float(underlying_value),
                        "close": float(underlying_value),
                    }
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _mock_optionchain(self, payload: Dict) -> Dict:
        """Mock option chain endpoint"""
        underlying = payload.get("underlying", "")
        exchange = payload.get("exchange", "")
        expiry_date = payload.get("expiry_date", "")
        strike_count = payload.get("strike_count", 10)
        
        # Parse expiry date (format: YYYYMMDD or YYYY-MM-DD)
        if expiry_date:
            try:
                if len(expiry_date) == 8:
                    expiry = datetime.strptime(expiry_date, "%Y%m%d")
                else:
                    expiry = datetime.strptime(expiry_date, "%Y-%m-%d")
            except:
                expiry = None
        else:
            expiry = None
        
        date = self.current_timestamp.date()
        
        try:
            chain_df = self.data_loader.get_options_chain(
                underlying,
                datetime.combine(date, datetime.min.time()),
                expiry
            )
            
            if chain_df.empty:
                return {"status": "error", "message": "No chain data found"}
            
            # Group by strike
            strikes = sorted(chain_df['Strike Price'].unique())[:strike_count]
            
            chain = []
            for strike in strikes:
                strike_data = {"strike": float(strike)}
                
                # Get CE data
                ce_row = chain_df[(chain_df['Strike Price'] == strike) & (chain_df['Option type'] == 'CE')]
                if not ce_row.empty:
                    ce = ce_row.iloc[0]
                    strike_data["ce"] = {
                        "symbol": f"{underlying}{int(strike)}CE",
                        "ltp": float(ce.get("LTP", ce.get("Close", 0))),
                        "open": float(ce.get("Open", 0)),
                        "high": float(ce.get("High", 0)),
                        "low": float(ce.get("Low", 0)),
                        "close": float(ce.get("Close", 0)),
                        "volume": int(ce.get("No. of contracts", 0)),
                        "oi": int(ce.get("Open Int", 0)) if pd.notna(ce.get("Open Int")) else 0,
                    }
                
                # Get PE data
                pe_row = chain_df[(chain_df['Strike Price'] == strike) & (chain_df['Option type'] == 'PE')]
                if not pe_row.empty:
                    pe = pe_row.iloc[0]
                    strike_data["pe"] = {
                        "symbol": f"{underlying}{int(strike)}PE",
                        "ltp": float(pe.get("LTP", pe.get("Close", 0))),
                        "open": float(pe.get("Open", 0)),
                        "high": float(pe.get("High", 0)),
                        "low": float(pe.get("Low", 0)),
                        "close": float(pe.get("Close", 0)),
                        "volume": int(pe.get("No. of contracts", 0)),
                        "oi": int(pe.get("Open Int", 0)) if pd.notna(pe.get("Open Int")) else 0,
                    }
                
                chain.append(strike_data)
            
            return {
                "status": "success",
                "chain": chain
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _mock_optiongreeks(self, payload: Dict) -> Dict:
        """Mock option Greeks endpoint"""
        symbol = payload.get("symbol", "")
        exchange = payload.get("exchange", "")
        
        underlying, strike, option_type = self._parse_option_symbol(symbol)
        
        if not underlying or not strike:
            return {"status": "error", "message": "Invalid option symbol"}
        
        date = self.current_timestamp.date()
        
        try:
            # Get option data
            df = self.data_loader.get_strike_data(
                underlying, option_type, strike,
                start_date=datetime.combine(date, datetime.min.time()),
                end_date=datetime.combine(date, datetime.max.time())
            )
            
            if df.empty:
                return {"status": "error", "message": "No data found"}
            
            row = df.iloc[-1]
            underlying_value = row.get("Underlying Value", 0)
            option_price = float(row.get("LTP", row.get("Close", 0)))
            
            # Simplified Greeks calculation (Black-Scholes approximation)
            # For backtesting, we use simplified formulas
            time_to_expiry = 1.0 / 365.0  # Assume 1 day to expiry (simplified)
            risk_free_rate = 0.06  # 6% annual
            
            # Estimate IV from price (simplified)
            iv = self._estimate_iv(underlying_value, strike, option_price, time_to_expiry, option_type == "CE")
            
            # Calculate simplified Greeks
            delta = self._calculate_delta(underlying_value, strike, time_to_expiry, iv, risk_free_rate, option_type == "CE")
            gamma = self._calculate_gamma(underlying_value, strike, time_to_expiry, iv, risk_free_rate)
            theta = self._calculate_theta(underlying_value, strike, time_to_expiry, iv, risk_free_rate, option_type == "CE")
            vega = self._calculate_vega(underlying_value, strike, time_to_expiry, iv, risk_free_rate)
            
            return {
                "status": "success",
                "symbol": symbol,
                "greeks": {
                    "delta": float(delta),
                    "gamma": float(gamma),
                    "theta": float(theta),
                    "vega": float(vega),
                },
                "implied_volatility": float(iv * 100)  # Convert to percentage
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _mock_history(self, payload: Dict) -> Dict:
        """Mock history endpoint"""
        symbol = payload.get("symbol", "")
        exchange = payload.get("exchange", "")
        interval = payload.get("interval", "1m")
        start_date_str = payload.get("start_date", "")
        end_date_str = payload.get("end_date", "")
        
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
        except:
            return {"status": "error", "message": "Invalid date format"}
        
        # Parse symbol
        underlying, strike, option_type = self._parse_option_symbol(symbol)
        
        try:
            if option_type:
                df = self.data_loader.get_strike_data(
                    underlying, option_type, strike,
                    start_date=start_date,
                    end_date=end_date
                )
            else:
                # Underlying - use first option's underlying value
                chain = self.data_loader.get_options_chain(underlying, start_date)
                if chain.empty:
                    return {"status": "error", "message": "No data found"}
                
                # Group by date and get underlying value
                df = chain.groupby('Date').agg({
                    'Underlying Value': 'first',
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'No. of contracts': 'sum'
                }).reset_index()
            
            if df.empty:
                return {"status": "error", "message": "No data found"}
            
            # Convert to OpenAlgo format
            candles = []
            for _, row in df.iterrows():
                candles.append({
                    "time": row['Date'].strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(row.get("Open", 0)),
                    "high": float(row.get("High", 0)),
                    "low": float(row.get("Low", 0)),
                    "close": float(row.get("Close", 0)),
                    "volume": int(row.get("No. of contracts", 0)),
                })
            
            return {
                "status": "success",
                "data": candles
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _mock_expiry(self, payload: Dict) -> Dict:
        """Mock expiry endpoint"""
        symbol = payload.get("symbol", "")
        exchange = payload.get("exchange", "")
        
        try:
            # Get available expiries from data
            df_ce = self.data_loader.load_file(symbol, "CE")
            if df_ce.empty:
                return {"status": "error", "message": "No data found"}
            
            expiries = sorted(df_ce['Expiry'].unique())
            
            # Format as YYYY-MM-DD
            expiry_list = [exp.strftime("%Y-%m-%d") for exp in expiries if pd.notna(exp)]
            
            return {
                "status": "success",
                "data": expiry_list
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _mock_optionsymbol(self, payload: Dict) -> Dict:
        """Mock option symbol endpoint"""
        # Similar to optionchain but returns symbol format
        return self._mock_optionchain(payload)
    
    def _parse_option_symbol(self, symbol: str) -> tuple:
        """
        Parse option symbol to extract underlying, strike, option type
        
        Examples:
            NIFTY25JAN202524500CE -> (NIFTY, 24500, CE)
            NIFTY25000CE -> (NIFTY, 25000, CE)
        """
        symbol = symbol.upper()
        
        # Try to find CE or PE at the end
        if symbol.endswith("CE"):
            option_type = "CE"
            base = symbol[:-2]
        elif symbol.endswith("PE"):
            option_type = "PE"
            base = symbol[:-2]
        else:
            return (symbol, None, None)
        
        # Extract strike (last digits before option type)
        # Find where digits start
        strike_str = ""
        for i in range(len(base) - 1, -1, -1):
            if base[i].isdigit():
                strike_str = base[i] + strike_str
            else:
                break
        
        if strike_str:
            strike = float(strike_str)
            underlying = base[:-len(strike_str)]
            return (underlying, strike, option_type)
        
        return (symbol, None, None)
    
    def _estimate_iv(self, S: float, K: float, price: float, T: float, is_call: bool) -> float:
        """Estimate implied volatility (simplified)"""
        # Simplified IV estimation using approximation
        # In production, use proper Black-Scholes inversion
        if price <= 0 or S <= 0:
            return 0.15  # Default 15%
        
        # Simple approximation
        moneyness = S / K if K > 0 else 1.0
        iv = 0.15 + abs(moneyness - 1.0) * 0.1  # Rough estimate
        return max(0.05, min(0.5, iv))
    
    def _calculate_delta(self, S: float, K: float, T: float, iv: float, r: float, is_call: bool) -> float:
        """Calculate delta (simplified approximation)"""
        import math
        
        if T <= 0 or iv <= 0 or K <= 0:
            return 0.5 if is_call else -0.5
        
        # Simplified delta approximation
        moneyness = S / K
        if is_call:
            # Call delta: higher when ITM
            if moneyness > 1.05:  # Deep ITM
                delta = 0.8 + (moneyness - 1.05) * 0.2
            elif moneyness < 0.95:  # Deep OTM
                delta = (moneyness - 0.90) * 0.2
            else:  # ATM
                delta = 0.4 + (moneyness - 0.95) * 4.0
            return min(1.0, max(0.0, delta))
        else:
            # Put delta: negative, more negative when ITM
            if moneyness < 0.95:  # Deep ITM
                delta = -0.8 - (0.95 - moneyness) * 0.2
            elif moneyness > 1.05:  # Deep OTM
                delta = -(moneyness - 1.05) * 0.2
            else:  # ATM
                delta = -0.4 - (1.05 - moneyness) * 4.0
            return max(-1.0, min(0.0, delta))
    
    def _calculate_gamma(self, S: float, K: float, T: float, iv: float, r: float) -> float:
        """Calculate gamma (simplified)"""
        if T <= 0 or iv <= 0 or S <= 0 or K <= 0:
            return 0.0
        
        # Gamma is highest at ATM
        moneyness = S / K
        distance_from_atm = abs(moneyness - 1.0)
        gamma = 0.01 / (1.0 + distance_from_atm * 10.0)  # Simplified
        return gamma
    
    def _calculate_theta(self, S: float, K: float, T: float, iv: float, r: float, is_call: bool) -> float:
        """Calculate theta (daily, simplified)"""
        if T <= 0 or iv <= 0:
            return -0.01  # Default daily theta
        
        # Theta increases as expiry approaches and is higher for ATM options
        moneyness = S / K if K > 0 else 1.0
        distance_from_atm = abs(moneyness - 1.0)
        
        # Base theta, higher for ATM
        base_theta = -0.02 / (1.0 + distance_from_atm * 5.0)
        
        # Increase as T decreases
        time_factor = 1.0 / (T * 365 + 1.0)
        
        return base_theta * time_factor
    
    def _calculate_vega(self, S: float, K: float, T: float, iv: float, r: float) -> float:
        """Calculate vega (simplified)"""
        if T <= 0 or iv <= 0 or S <= 0:
            return 0.0
        
        # Vega is highest at ATM and increases with time
        moneyness = S / K if K > 0 else 1.0
        distance_from_atm = abs(moneyness - 1.0)
        
        vega = S * 0.01 * math.sqrt(T) / (1.0 + distance_from_atm * 5.0)
        return vega / 100  # Divide by 100 for 1% IV change


# Global mock instance (set per timestamp)
_current_mock: Optional[OpenAlgoAPIMock] = None

def set_current_timestamp(timestamp: datetime):
    """Set current timestamp for API mock"""
    global _current_mock
    _current_mock = OpenAlgoAPIMock(timestamp)

def get_mock() -> Optional[OpenAlgoAPIMock]:
    """Get current API mock instance"""
    return _current_mock
