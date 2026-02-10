import json
import logging
import time
from datetime import datetime

from utils import httpx_client

logger = logging.getLogger("OptionChainUtils")

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default

def normalize_expiry(expiry_date):
    """Normalize expiry date format."""
    # Placeholder: assume format is correct or implement robust parsing if needed
    return expiry_date

def choose_nearest_expiry(dates):
    """Choose the nearest expiry date from a list of dates."""
    if not dates:
        return None
    # Sort dates? Assume format allows sorting or they come sorted
    # For simplicity, return the first one as it's usually the nearest in API responses
    return dates[0]

def is_chain_valid(chain_resp, min_strikes=8):
    """Check if option chain response is valid."""
    if not chain_resp or chain_resp.get("status") != "success":
        return False, "API Error or Empty Response"

    chain = chain_resp.get("chain", [])
    if not chain:
        return False, "Empty Chain Data"

    if len(chain) < min_strikes:
        return False, f"Insufficient Strikes: {len(chain)} < {min_strikes}"

    return True, "Valid"

def get_atm_strike(chain):
    """Finds ATM strike from chain data."""
    # Assuming chain is sorted or we search for label="ATM"
    for item in chain:
        if item.get("ce", {}).get("label") == "ATM":
            return item["strike"]
    # Fallback: find strike closest to underlying_ltp if available?
    # For now, stick to label logic as in strategies
    return None

def calculate_straddle_premium(chain, atm_strike):
    """Calculates combined premium of ATM CE and PE."""
    ce_ltp = 0.0
    pe_ltp = 0.0

    for item in chain:
        if item["strike"] == atm_strike:
            ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
            pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
            break

    return ce_ltp + pe_ltp

def get_leg_details(chain, offset, option_type, quantity=1, product="MIS"):
    """Helper to resolve symbol and LTP from chain based on offset."""
    # OTM2 CE means finding label="OTM2" in CE dict
    for item in chain:
        opt = item.get(option_type.lower(), {})
        if opt.get("label") == offset:
            return {
                "symbol": opt.get("symbol"),
                "ltp": safe_float(opt.get("ltp", 0)),
                "quantity": quantity,
                "product": product
                # Action is determined by strategy logic
            }
    return None

def check_time_window(start_time_str, end_time_str):
    """Checks if current time is within entry window."""
    now = datetime.now().time()
    try:
        start = datetime.strptime(start_time_str, "%H:%M").time()
        end = datetime.strptime(end_time_str, "%H:%M").time()
        return start <= now <= end
    except ValueError:
        logger.error(f"Invalid time format in configuration: start={start_time_str}, end={end_time_str}")
        return False

class OptionChainClient:
    def __init__(self, api_key, host):
        self.api_key = api_key
        self.host = host.rstrip('/')

    def expiry(self, underlying, exchange, instrument_type="options"):
        url = f"{self.host}/api/v1/expiry"
        payload = {
            "underlying": underlying,
            "exchange": exchange,
            "instrument": instrument_type,
            "apikey": self.api_key
        }
        try:
            response = httpx_client.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def optionchain(self, underlying, exchange, expiry_date, strike_count=10):
        url = f"{self.host}/api/v1/optionchain"
        payload = {
            "underlying": underlying,
            "exchange": exchange,
            "expiry": expiry_date,
            "strike_count": strike_count,
            "apikey": self.api_key
        }
        try:
            response = httpx_client.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def optionsmultiorder(self, strategy, underlying, exchange, expiry_date, legs):
        url = f"{self.host}/api/v1/optionsmultiorder"
        payload = {
            "strategy": strategy,
            "underlying": underlying,
            "exchange": exchange,
            "expiry": expiry_date,
            "legs": legs,
            "apikey": self.api_key
        }
        try:
            response = httpx_client.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

class OptionPositionTracker:
    def __init__(self, sl_pct, tp_pct, max_hold_min):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min
        self.open_legs = []
        self.entry_time = None
        self.entry_prices = {} # Map symbol -> price
        self.side = None # "BUY" or "SELL" (Net)

    def add_legs(self, legs, entry_prices, side):
        """
        Track new position legs.
        legs: List of dicts with leg details
        entry_prices: List of prices corresponding to legs
        side: "BUY" (Debit) or "SELL" (Credit)
        """
        self.open_legs = legs
        self.side = side
        self.entry_time = time.time()

        # Store entry prices
        for i, leg in enumerate(legs):
            # If entry_prices is passed as list matching legs
            price = entry_prices[i] if i < len(entry_prices) else 0.0
            self.entry_prices[leg['symbol']] = price

    def clear(self):
        self.open_legs = []
        self.entry_time = None
        self.entry_prices = {}
        self.side = None

    def should_exit(self, chain):
        """
        Check exit conditions (SL, TP, Time).
        Returns: (exit_now, legs_to_exit, reason)
        """
        if not self.open_legs:
            return False, [], ""

        # Calculate current PnL
        current_pnl = 0.0
        total_entry_premium = 0.0

        # We need to find current prices for open legs from chain
        # Create map of symbol -> ltp from chain
        symbol_ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"):
                symbol_ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"):
                symbol_ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        for leg in self.open_legs:
            symbol = leg['symbol']
            entry_price = self.entry_prices.get(symbol, 0.0)
            current_price = symbol_ltp_map.get(symbol, entry_price) # Fallback to entry if not found
            qty = leg.get('quantity', 1) # Assume 1 if not set, but usually passed

            leg_action = leg.get('action', 'BUY')

            if leg_action == "BUY":
                # Long: Profit if Price > Entry
                current_pnl += (current_price - entry_price) * qty
                total_entry_premium += entry_price * qty
            else:
                # Short: Profit if Price < Entry
                current_pnl += (entry_price - current_price) * qty
                total_entry_premium += entry_price * qty # For ROI calculation base?

        # Check Time Exit
        if self.entry_time and (time.time() - self.entry_time) / 60 >= self.max_hold_min:
             return True, self.open_legs, f"Max Hold Time ({self.max_hold_min}m) Reached"

        # Check SL/TP based on PnL vs Total Premium (ROI) or fixed points?
        # Strategy uses sl_pct of premium

        # If Credit Strategy (SELL side dominant):
        # We collected premium. Max profit is premium.
        # SL is usually % of collected premium.

        # Simple ROI check:
        roi_pct = 0
        if total_entry_premium > 0:
            roi_pct = (current_pnl / total_entry_premium) * 100

        if roi_pct <= -self.sl_pct:
            return True, self.open_legs, f"Stop Loss Hit: {roi_pct:.2f}% <= -{self.sl_pct}%"

        if roi_pct >= self.tp_pct:
            return True, self.open_legs, f"Target Profit Hit: {roi_pct:.2f}% >= {self.tp_pct}%"

        return False, [], ""
