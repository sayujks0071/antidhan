import requests
import time
from datetime import datetime, timedelta

def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(float(value))
    except (ValueError, TypeError):
        return default

def normalize_expiry(expiry_date):
    """Normalizes expiry date string to DDMMMYY format (e.g., 14FEB26)."""
    if not expiry_date:
        return None
    try:
        # If already in format, return as is (uppercase)
        # Check if it matches expected format length roughly
        expiry_date = expiry_date.strip().upper()
        datetime.strptime(expiry_date, "%d%b%y")
        return expiry_date
    except ValueError:
        pass

    # Try other formats if needed, but usually API returns DDMMMYY
    return expiry_date

def choose_nearest_expiry(expiry_dates):
    """
    Selects the nearest future expiry date from a list of strings (DDMMMYY).
    """
    if not expiry_dates:
        return None

    today = datetime.now().date()
    valid_dates = []

    for d_str in expiry_dates:
        try:
            d_date = datetime.strptime(d_str, "%d%b%y").date()
            if d_date >= today:
                valid_dates.append((d_date, d_str))
        except ValueError:
            continue

    if not valid_dates:
        return None

    # Sort by date and return the string of the earliest one
    valid_dates.sort(key=lambda x: x[0])
    return valid_dates[0][1]


def choose_monthly_expiry(expiry_dates):
    """
    Selects the nearest monthly expiry date (last expiry of the month).
    """
    if not expiry_dates:
        return None

    today = datetime.now().date()
    future_dates = []

    for d_str in expiry_dates:
        try:
            d_date = datetime.strptime(d_str, "%d%b%y").date()
            if d_date >= today:
                future_dates.append((d_date, d_str))
        except ValueError:
            continue

    if not future_dates:
        return None

    # Group by (Year, Month) and find the max date in each group
    monthly_expiries = {}
    for d_date, d_str in future_dates:
        key = (d_date.year, d_date.month)
        if key not in monthly_expiries:
            monthly_expiries[key] = (d_date, d_str)
        else:
            # Update if current date is greater than stored date for this month
            if d_date > monthly_expiries[key][0]:
                monthly_expiries[key] = (d_date, d_str)

    # Collect all monthly expiries
    final_candidates = list(monthly_expiries.values())

    if not final_candidates:
        return None

    # Sort by date and return the earliest one
    final_candidates.sort(key=lambda x: x[0])
    return final_candidates[0][1]

def is_chain_valid(chain_response, min_strikes=10, require_oi=True, require_volume=False):
    """
    Validates option chain response.
    Returns (bool, reason_string)
    """
    if not chain_response or chain_response.get("status") != "success":
        return False, "API Error or Invalid Response"

    chain = chain_response.get("chain", [])
    if not chain:
        return False, "Empty Chain"

    if len(chain) < min_strikes:
        return False, f"Insufficient Strikes: {len(chain)} < {min_strikes}"

    # Check if data looks populated (LTP > 0 for at least some strikes)
    # And specifically for OI/Volume if requested

    valid_strikes = 0
    for item in chain:
        ce = item.get("ce", {})
        pe = item.get("pe", {})

        # Check basic LTP validity
        if safe_float(ce.get("ltp")) > 0 or safe_float(pe.get("ltp")) > 0:
            valid_strikes += 1

    if valid_strikes < min_strikes // 2:
        return False, "Chain Data Seems Stale/Empty (LTPs are 0)"

    return True, "OK"

def get_atm_strike(chain):
    """Finds ATM strike from chain data."""
    # Assuming chain is sorted or we search for label="ATM"
    for item in chain:
        if item.get("ce", {}).get("label") == "ATM":
            return item["strike"]
    # Fallback using spot price if available in metadata (not passed here usually)
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

class OptionChainClient:
    def __init__(self, api_key, host="http://127.0.0.1:5000"):
        self.api_key = api_key
        self.host = host.rstrip('/')
        self.session = requests.Session()

    def _post(self, endpoint, payload):
        url = f"{self.host}/api/v1/{endpoint}"
        payload["apikey"] = self.api_key
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"API Error ({endpoint}): {e}", flush=True)
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
        self.open_legs = []     # List of dicts: {symbol, action, entry_price, quantity, ...}
        self.entry_time = None
        self.side = None        # "BUY" or "SELL" (net position bias)

    def add_legs(self, legs, entry_prices, side):
        """
        legs: List of leg details dicts (must contain 'symbol', 'action', 'quantity')
        entry_prices: List of entry prices corresponding to legs
        side: "BUY" (Net Long/Debit) or "SELL" (Net Short/Credit)
        """
        self.open_legs = []
        self.entry_time = datetime.now()
        self.side = side.upper()

        for i, leg in enumerate(legs):
            leg_data = leg.copy()
            leg_data["entry_price"] = safe_float(entry_prices[i])
            self.open_legs.append(leg_data)

    def should_exit(self, chain):
        """
        Checks exit conditions based on current chain data.
        Returns: (bool exit_now, list legs, string reason)
        """
        if not self.open_legs:
            return False, [], ""

        # 1. Time Stop
        minutes_held = (datetime.now() - self.entry_time).total_seconds() / 60
        if minutes_held >= self.max_hold_min:
            return True, self.open_legs, "time_stop"

        # 2. PnL Check
        total_entry_val = 0.0
        total_curr_val = 0.0

        # Calculate total value of the spread/condor
        # For SELL strategy (Credit): Entry > Current is Profit
        # For BUY strategy (Debit): Current > Entry is Profit

        # We need to map chain LTPs to our legs
        # Create a lookup map: symbol -> ltp
        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        # Calculate PnL per leg
        # Note: quantities are assumed equal for pct calc simplification,
        # but properly we should weigh by quantity.

        current_pnl_pct = 0.0

        # We will track aggregate premium
        # e.g., Iron Condor: Sold @ 100+100=200. Bought @ 20+20=40. Net Credit = 160.
        # If Net Credit shrinks, we profit.

        net_entry_premium = 0.0
        net_current_premium = 0.0

        for leg in self.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            curr = ltp_map.get(sym, entry) # Fallback to entry if no LTP found (neutral)
            qty = leg.get("quantity", 1)

            action = leg["action"].upper()

            if action == "SELL":
                net_entry_premium += entry
                net_current_premium += curr
            else: # BUY
                net_entry_premium -= entry
                net_current_premium -= curr

        # Calculate PnL based on Strategy Side
        # side="SELL" implies we want Net Premium to DECREASE (if net credit)
        # or implies we are Net Short Options.

        # Let's simplify:
        # PnL = (Entry - Current) for SELL
        # PnL = (Current - Entry) for BUY

        # Wait, strictly speaking:
        # PnL = Sum(Sell_Entry - Sell_Curr) + Sum(Buy_Curr - Buy_Entry)

        pnl = 0.0
        total_initial_premium_abs = 0.0 # To calculate percentage

        for leg in self.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            curr = ltp_map.get(sym, entry)

            if leg["action"].upper() == "SELL":
                pnl += (entry - curr)
                total_initial_premium_abs += entry
            else:
                pnl += (curr - entry)
                total_initial_premium_abs += entry # Add to basis for % calculation?
                # Usually SL% is based on the premium collected (for credit) or paid (for debit).

        # If total_initial_premium_abs is 0, avoid div by zero
        if total_initial_premium_abs == 0:
            return False, [], ""

        pnl_pct = (pnl / total_initial_premium_abs) * 100

        # Check Stops
        # SL: pnl_pct < -SL_PCT
        if pnl_pct <= -self.sl_pct:
            return True, self.open_legs, f"stop_loss_hit ({pnl_pct:.1f}%)"

        # TP: pnl_pct > TP_PCT
        if pnl_pct >= self.tp_pct:
            return True, self.open_legs, f"take_profit_hit ({pnl_pct:.1f}%)"

        return False, [], ""

    def clear(self):
        self.open_legs = []
        self.entry_time = None
        self.side = None
