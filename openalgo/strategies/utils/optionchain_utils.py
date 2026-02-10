import requests
import time
from datetime import datetime
import logging

# Configure basic logging if not already configured
logger = logging.getLogger("OptionChainUtils")

def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

def normalize_expiry(expiry_date):
    """
    Normalizes expiry date to DDMMMYY format (e.g. 14FEB26).
    Input can be YYYY-MM-DD or DD-MMM-YYYY etc.
    For now, assumes input is already correct or simple string.
    """
    if not expiry_date:
        return ""
    return expiry_date.upper()

def choose_nearest_expiry(dates):
    """
    Selects the nearest future expiry date from a list of strings.
    Assumes format DDMMMYY (e.g. 14FEB26).
    """
    if not dates:
        return None

    future_dates = []
    now = datetime.now().date()

    for d_str in dates:
        try:
            # Try parsing DDMMMYY
            dt = datetime.strptime(d_str, "%d%b%y").date()
            if dt >= now:
                future_dates.append((dt, d_str))
        except ValueError:
            pass

    if not future_dates:
        return None

    # Sort by date
    future_dates.sort(key=lambda x: x[0])
    return future_dates[0][1]

def is_chain_valid(chain_resp, min_strikes=5, require_oi=False, require_volume=False):
    """
    Validates option chain response.
    Returns (bool, reason).
    """
    if not chain_resp or chain_resp.get("status") != "success":
        return False, "api_error"

    chain = chain_resp.get("chain", [])
    if len(chain) < min_strikes:
        return False, "insufficient_strikes"

    underlying_ltp = safe_float(chain_resp.get("underlying_ltp"))
    if underlying_ltp <= 0:
        return False, "invalid_underlying_ltp"

    # Check if ATM data exists
    has_atm = any(item.get("ce", {}).get("label") == "ATM" for item in chain)
    if not has_atm:
        return False, "atm_missing"

    return True, "ok"


class OptionChainClient:
    def __init__(self, api_key, host="http://127.0.0.1:5000"):
        self.api_key = api_key
        self.host = host.rstrip("/")

    def _post(self, endpoint, payload):
        url = f"{self.host}/api/v1/{endpoint}"
        payload["apikey"] = self.api_key
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def expiry(self, underlying, exchange, type_="options"):
        return self._post("expiry", {
            "underlying": underlying,
            "exchange": exchange,
            "type": type_
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
        legs: list of dicts with offset, option_type, action, quantity, product
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

        self.open_legs = []
        self.entry_time = 0
        self.side = "SELL" # Default
        self.initial_value = 0.0 # Net premium/value

    def add_legs(self, legs, entry_prices, side="SELL"):
        """
        legs: list of dicts (symbol, action, quantity)
        entry_prices: list of floats corresponding to legs
        side: "SELL" (Credit) or "BUY" (Debit)
        """
        self.open_legs = []
        self.side = side
        self.entry_time = time.time()

        net_val = 0.0

        for i, leg in enumerate(legs):
            price = entry_prices[i]
            qty = leg.get("quantity", 1)
            action = leg.get("action", "BUY")

            leg_data = leg.copy()
            leg_data["entry_price"] = price
            self.open_legs.append(leg_data)

            # Calculate initial value contribution
            # If side is SELL (Credit strategy), we expect positive net value from Shorts
            # Value = Price * Qty
            # Contribution to Net Cash Flow:
            # Sell: +Price
            # Buy: -Price

            if action == "SELL":
                net_val += price * qty
            else:
                net_val -= price * qty

        # If side is SELL, we track Credit. If side is BUY, we track Debit (cost).
        # Usually for Buy, net_val is negative (Debit). We store absolute cost.
        if side == "BUY":
            self.initial_value = -net_val
        else:
            self.initial_value = net_val

    def clear(self):
        self.open_legs = []
        self.initial_value = 0.0
        self.entry_time = 0

    def should_exit(self, chain):
        """
        Checks exit conditions.
        Returns (bool, legs_to_close, reason)
        """
        if not self.open_legs:
            return False, [], ""

        # 1. Check Time Stop
        if self.max_hold_min > 0:
            elapsed = (time.time() - self.entry_time) / 60
            if elapsed >= self.max_hold_min:
                return True, self.open_legs, "time_stop"

        # 2. Calculate Current Value & PnL
        current_net_val = 0.0

        # Build map of symbol -> ltp
        # Chain structure: list of items with ce/pe dicts
        symbol_map = {}
        for item in chain:
            ce = item.get("ce", {})
            if ce and "symbol" in ce:
                symbol_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            pe = item.get("pe", {})
            if pe and "symbol" in pe:
                symbol_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        # Calculate current value
        for leg in self.open_legs:
            sym = leg["symbol"]
            price = symbol_map.get(sym, leg["entry_price"]) # Fallback to entry if not found? Or 0?
            qty = leg.get("quantity", 1)
            action = leg.get("action", "BUY")

            # Cash flow to CLOSE
            # If we Sold (Short), we need to Buy (Pay price) -> -Price
            # If we Bought (Long), we need to Sell (Receive price) -> +Price

            if action == "SELL":
                current_net_val -= price * qty
            else:
                current_net_val += price * qty

        # PnL = Initial Net Cash Flow + Current Net Cash Flow (to close)
        # Initial Cash Flow:
        # Sell: +Entry
        # Buy: -Entry
        # (This is already captured in self.initial_value logic? Wait.)

        # Let's redo PnL logic simply:
        # PnL = Value_Now - Value_Entry (For Long)
        # PnL = Value_Entry - Value_Now (For Short/Credit)

        # Actually:
        # PnL = Sum( (Exit_Price - Entry_Price) * Qty * (1 if Buy else -1) )

        pnl = 0.0
        current_value_abs = 0.0 # For ROI calc?

        for leg in self.open_legs:
            sym = leg["symbol"]
            curr_price = symbol_map.get(sym, leg["entry_price"])
            entry_price = leg["entry_price"]
            qty = leg.get("quantity", 1)
            action = leg.get("action", "BUY")

            if action == "BUY":
                pnl += (curr_price - entry_price) * qty
            else:
                pnl += (entry_price - curr_price) * qty

        # ROI %
        # Base is self.initial_value (Net Premium or Debit)
        # If base is small (e.g. Iron Fly with low risk), % can be huge.
        # But usually we use the collected premium or paid premium as base.

        if self.initial_value == 0:
            roi = 0
        else:
            roi = (pnl / abs(self.initial_value)) * 100

        # Check SL/TP
        # SL is a LOSS. roi <= -sl_pct
        if roi <= -self.sl_pct:
            return True, self.open_legs, f"stop_loss_{roi:.2f}%"

        # TP is a GAIN. roi >= tp_pct
        if roi >= self.tp_pct:
            return True, self.open_legs, f"take_profit_{roi:.2f}%"

        return False, [], ""
