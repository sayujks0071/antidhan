import logging
import time
from datetime import datetime
import requests
import json

# Configure logging
logger = logging.getLogger("OptionChainUtils")

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def normalize_expiry(expiry_date):
    """Normalize expiry date format if needed."""
    if not expiry_date:
        return None
    return expiry_date.upper()

def choose_nearest_expiry(expiry_list):
    """
    Choose the nearest expiry from a list of expiry strings (e.g., "14FEB26").
    Assumes format DDMMMYY.
    """
    if not expiry_list:
        return None

    today = datetime.now().date()
    future_expiries = []

    for exp_str in expiry_list:
        try:
            # Parse DDMMMYY like 14FEB26
            exp_date = datetime.strptime(exp_str, "%d%b%y").date()
            if exp_date >= today:
                future_expiries.append((exp_date, exp_str))
        except ValueError:
            continue

    if not future_expiries:
        return None

    # Sort by date and return the string of the earliest one
    future_expiries.sort(key=lambda x: x[0])
    return future_expiries[0][1]

def is_chain_valid(chain_resp, min_strikes=10, require_oi=True, require_volume=False):
    """
    Validate option chain response.
    Returns: (valid: bool, reason: str)
    """
    if not chain_resp or chain_resp.get("status") != "success":
        return False, "chain_status_error"

    chain = chain_resp.get("chain", [])
    if not chain:
        return False, "empty_chain"

    if len(chain) < min_strikes:
        return False, "insufficient_strikes"

    underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))
    if underlying_ltp <= 0:
        return False, "underlying_ltp_invalid"

    atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)
    if not atm_item:
        return False, "atm_missing"

    if require_oi:
        total_oi = sum(safe_int((item.get("ce") or {}).get("oi")) + safe_int((item.get("pe") or {}).get("oi")) for item in chain)
        if total_oi == 0:
            return False, "oi_unavailable"

    return True, "ok"

class OptionChainClient:
    def __init__(self, api_key, host="http://127.0.0.1:5000"):
        self.api_key = api_key
        self.host = host.rstrip("/")
        self.headers = {"Content-Type": "application/json"}

    def expiry(self, underlying, exchange, instrument_type="options"):
        url = f"{self.host}/api/v1/expiry"
        payload = {
            "apikey": self.api_key,
            "underlying": underlying,
            "exchange": exchange,
            "instrument_type": instrument_type
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching expiry: {e}")
            return {"status": "error", "message": str(e)}

    def optionchain(self, underlying, exchange, expiry_date, strike_count=10):
        url = f"{self.host}/api/v1/optionchain"
        payload = {
            "apikey": self.api_key,
            "underlying": underlying,
            "symbol": underlying,
            "exchange": exchange,
            "expiry": expiry_date,
            "strike_count": strike_count
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching option chain: {e}")
            return {"status": "error", "message": str(e)}

    def optionsmultiorder(self, strategy, underlying, exchange, expiry_date, legs):
        url = f"{self.host}/api/v1/optionsmultiorder"
        payload = {
            "apikey": self.api_key,
            "strategy": strategy,
            "underlying": underlying,
            "exchange": exchange,
            "expiry": expiry_date,
            "legs": legs
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=30)
            return resp.json()
        except Exception as e:
            logger.error(f"Error placing multi-leg order: {e}")
            return {"status": "error", "message": str(e)}

class OptionPositionTracker:
    def __init__(self, sl_pct, tp_pct, max_hold_min=None):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min
        self.legs = []  # List of dicts: {symbol, entry_price, side, entry_time}
        self.entry_time = None
        self.strategy_side = "SELL" # Default

    @property
    def open_legs(self):
        return bool(self.legs)

    def add_legs(self, leg_definitions, entry_prices, side="SELL"):
        """
        leg_definitions: list of leg dicts (from order config)
        entry_prices: dict mapping symbol -> price
        side: 'BUY' or 'SELL' (overall strategy direction)
        """
        self.entry_time = datetime.now()
        self.strategy_side = side
        self.legs = []
        for leg in leg_definitions:
            symbol = leg.get("symbol")
            if not symbol:
                continue # Skip legs without symbol

            entry_price = entry_prices.get(symbol, 0.0)
            new_leg = leg.copy()
            new_leg["entry_price"] = entry_price
            self.legs.append(new_leg)

    def should_exit(self, chain):
        """
        Check if we should exit based on SL/TP/Time.
        chain: The current option chain data (list of dicts).
        Returns: exit_now (bool), legs (list), reason (str)
        """
        if not self.legs:
            return False, [], "no_position"

        # 1. Check Time Stop
        if self.max_hold_min and self.entry_time:
            elapsed_min = (datetime.now() - self.entry_time).total_seconds() / 60
            if elapsed_min >= self.max_hold_min:
                return True, self.legs, "time_stop"

        # 2. Check SL/TP
        # Create symbol -> ltp map
        symbol_ltp = {}
        for item in chain:
            for type_ in ["ce", "pe"]:
                data = item.get(type_)
                if data and "symbol" in data:
                    symbol_ltp[data["symbol"]] = safe_float(data.get("ltp"))

        total_entry_premium = 0.0
        total_current_premium = 0.0

        missing_price = False

        for leg in self.legs:
            sym = leg.get("symbol")
            entry = leg.get("entry_price", 0.0)
            qty = safe_float(leg.get("quantity", 1))

            ltp = symbol_ltp.get(sym)
            if ltp is None:
                # If symbol not found in chain (e.g. far OTM not in current view), we can't calculate PnL
                missing_price = True
                continue

            total_entry_premium += entry * qty
            total_current_premium += ltp * qty

        if missing_price:
            # Can't calculate full PnL if any leg price is missing
            return False, [], "waiting_for_prices"

        # Avoid division by zero
        if total_entry_premium == 0:
            return False, [], "hold" # Should not happen if we entered correctly

        # Logic for SELL strategy (Short Premium / Credit Strategy)
        if self.strategy_side == "SELL":
            # SL: Premium RISES
            if total_current_premium >= total_entry_premium * (1 + self.sl_pct / 100):
                 return True, self.legs, "stop_loss"

            # TP: Premium DROPS
            if total_current_premium <= total_entry_premium * (1 - self.tp_pct / 100):
                 return True, self.legs, "take_profit"

        # Logic for BUY strategy (Long Premium / Debit Strategy)
        else:
            # SL: Premium DROPS
            if total_current_premium <= total_entry_premium * (1 - self.sl_pct / 100):
                return True, self.legs, "stop_loss"

            # TP: Premium RISES
            if total_current_premium >= total_entry_premium * (1 + self.tp_pct / 100):
                return True, self.legs, "take_profit"

        return False, [], "hold"

    def clear(self):
        self.legs = []
        self.entry_time = None
