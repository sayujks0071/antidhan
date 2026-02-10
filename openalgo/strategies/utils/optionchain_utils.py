import requests
import time
from datetime import datetime, timedelta

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
    """
    Normalizes expiry date to DDMMMYY format (e.g., 10FEB26).
    """
    if not expiry_date:
        return None
    try:
        # If already in DDMMMYY format, return as is (upper)
        if len(expiry_date) == 7 and expiry_date[2:5].isalpha():
            return expiry_date.upper()

        # Try parsing from YYYY-MM-DD
        dt = datetime.strptime(expiry_date, "%Y-%m-%d")
        return dt.strftime("%d%b%y").upper()
    except ValueError:
        return expiry_date.upper()

def choose_nearest_expiry(expiry_list):
    """
    Selects the nearest expiry date from a list of strings.
    """
    if not expiry_list:
        return None

    today = datetime.now().date()
    candidates = []

    for exp in expiry_list:
        try:
            # Parse DDMMMYY
            dt = datetime.strptime(exp, "%d%b%y").date()
            if dt >= today:
                candidates.append((dt, exp))
        except ValueError:
            continue

    if not candidates:
        return None

    # Sort by date
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]

def is_chain_valid(chain_resp, min_strikes=10, require_oi=True, require_volume=False):
    """
    Validates option chain response.
    """
    if not chain_resp or chain_resp.get("status") != "success":
        return False, "API Error or Empty Response"

    chain = chain_resp.get("chain", [])
    if len(chain) < min_strikes:
        return False, f"Insufficient strikes: {len(chain)} < {min_strikes}"

    # Check for valid data in ATM strike
    atm_found = False
    for item in chain:
        ce = item.get("ce", {})
        pe = item.get("pe", {})

        if ce.get("label") == "ATM":
            atm_found = True
            if require_oi and (safe_int(ce.get("oi")) == 0 or safe_int(pe.get("oi")) == 0):
                return False, "Zero OI at ATM"
            if require_volume and (safe_int(ce.get("volume")) == 0 or safe_int(pe.get("volume")) == 0):
                return False, "Zero Volume at ATM"
            break

    if not atm_found:
        return False, "ATM strike not found"

    return True, "Valid"

class OptionChainClient:
    def __init__(self, api_key, host="http://127.0.0.1:5000"):
        self.api_key = api_key
        self.host = host.rstrip("/")
        self.session = requests.Session()

    def _post(self, endpoint, payload):
        url = f"{self.host}/api/v1/{endpoint}"
        payload["apikey"] = self.api_key
        try:
            resp = self.session.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def expiry(self, underlying, exchange, instrument_type="options"):
        return self._post("expiry", {
            "underlying": underlying,
            "exchange": exchange,
            "instrument_type": instrument_type
        })

    def optionchain(self, underlying, exchange, expiry_date, strike_count=10):
        return self._post("optionchain", {
            "underlying": underlying,
            "exchange": exchange,
            "expiry_date": expiry_date,
            "strike_count": strike_count
        })

    def optionsmultiorder(self, strategy, underlying, exchange, expiry_date, legs):
        """
        Place multi-leg option order.
        legs: list of dicts with keys: offset, option_type, action, quantity, product
        """
        return self._post("optionsmultiorder", {
            "strategy": strategy,
            "underlying": underlying,
            "exchange": exchange,
            "expiry_date": expiry_date,
            "legs": legs
        })

class OptionPositionTracker:
    def __init__(self, sl_pct, tp_pct, max_hold_min):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min
        self.open_legs = [] # List of dicts: symbol, action, quantity, entry_price, entry_time
        self.entry_time = None
        self.side = None # "BUY" or "SELL" (net)

    def add_legs(self, legs, entry_prices, side):
        """
        legs: List of dicts with 'symbol', 'action', 'quantity'
        entry_prices: List of floats corresponding to legs
        side: 'BUY' (Net Debit) or 'SELL' (Net Credit)
        """
        self.open_legs = []
        self.entry_time = datetime.now()
        self.side = side.upper()

        for i, leg in enumerate(legs):
            self.open_legs.append({
                "symbol": leg["symbol"],
                "action": leg["action"],
                "quantity": leg["quantity"],
                "entry_price": entry_prices[i],
                "product": leg.get("product", "MIS")
            })

    def should_exit(self, chain):
        """
        Checks exit conditions based on current chain prices.
        Returns: (bool exit_now, list legs, str reason)
        """
        if not self.open_legs:
            return False, [], ""

        # 1. Check Time Stop
        if self.max_hold_min > 0:
            elapsed = (datetime.now() - self.entry_time).total_seconds() / 60
            if elapsed >= self.max_hold_min:
                return True, self.open_legs, "time_stop"

        # 2. Calculate PnL
        total_entry_premium = 0.0
        current_premium = 0.0

        # Build map of symbol -> ltp from chain
        price_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): price_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): price_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        pnl = 0.0
        missing_price = False

        for leg in self.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            qty = leg["quantity"]

            if sym not in price_map:
                missing_price = True
                break

            curr = price_map[sym]

            if leg["action"] == "BUY":
                pnl += (curr - entry) * qty
                total_entry_premium += entry * qty # Debit
            else: # SELL
                pnl += (entry - curr) * qty
                total_entry_premium += entry * qty # Credit (risk basis usually calls for margin, but here we track premium capture)

        if missing_price:
            return False, [], "" # Can't calculate, hold

        # PnL Percentage logic
        # If Net Credit (SELL), PnL is positive if premium drops.
        # SL is if PnL is negative beyond SL% of collected premium.
        # TP is if PnL is positive beyond TP% of collected premium.

        # If Net Debit (BUY), PnL is positive if premium rises.
        # SL is if PnL is negative beyond SL% of paid premium.
        # TP is if PnL is positive beyond TP% of paid premium.

        pnl_pct = (pnl / total_entry_premium) * 100 if total_entry_premium > 0 else 0

        if pnl_pct <= -self.sl_pct:
            return True, self.open_legs, "stop_loss"

        if pnl_pct >= self.tp_pct:
            return True, self.open_legs, "take_profit"

        return False, [], ""

    def clear(self):
        self.open_legs = []
        self.entry_time = None
        self.side = None
