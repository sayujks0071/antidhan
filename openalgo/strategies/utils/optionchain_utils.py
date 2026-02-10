import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
import requests

# Configure logging if not already configured
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
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
    """
    Normalizes expiry date format to DDMMMYY (e.g., 10FEB26).
    """
    if not expiry_date:
        return None
    try:
        # Try parsing various formats if needed, but assuming input is standard
        # If input is YYYY-MM-DD, convert.
        # If input is DDMMMYY, return as is.
        if "-" in expiry_date:
            d = datetime.strptime(expiry_date, "%Y-%m-%d")
            return d.strftime("%d%b%y").upper()
        return expiry_date.upper()
    except Exception:
        return expiry_date

def choose_nearest_expiry(expiry_list):
    """
    Selects the nearest expiry date from a list of strings (DDMMMYY).
    """
    if not expiry_list:
        return None

    today = datetime.now().date()
    valid_dates = []

    for exp_str in expiry_list:
        try:
            # Parse DDMMMYY
            d = datetime.strptime(exp_str, "%d%b%y").date()
            if d >= today:
                valid_dates.append((d, exp_str))
        except ValueError:
            continue

    if not valid_dates:
        return None

    # Sort by date
    valid_dates.sort(key=lambda x: x[0])
    return valid_dates[0][1]

def is_chain_valid(chain_resp, min_strikes=5, require_oi=True, require_volume=False):
    """
    Validates option chain response.
    Returns: (bool, reason)
    """
    if not chain_resp or chain_resp.get("status") != "success":
        return False, f"API Error: {chain_resp.get('message') if chain_resp else 'No response'}"

    chain = chain_resp.get("chain", [])
    if not chain:
        return False, "Empty chain data"

    if len(chain) < min_strikes:
        return False, f"Insufficient strikes: {len(chain)} < {min_strikes}"

    # Check liquidity for ATM
    atm_found = False
    for item in chain:
        ce = item.get("ce", {})
        pe = item.get("pe", {})

        if ce.get("label") == "ATM" or pe.get("label") == "ATM":
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

    def expiry(self, underlying, exchange="NSE", instrument_type="options"):
        url = f"{self.host}/api/v1/expiry"
        payload = {
            "apikey": self.api_key,
            "underlying": underlying,
            "exchange": exchange,
            "instrument_type": instrument_type
        }
        try:
            resp = self.session.post(url, json=payload, timeout=30.0)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def optionchain(self, underlying, exchange, expiry_date, strike_count=10):
        url = f"{self.host}/api/v1/optionchain"
        payload = {
            "apikey": self.api_key,
            "underlying": underlying,
            "exchange": exchange,
            "expiry_date": expiry_date,
            "strike_count": strike_count
        }
        try:
            resp = self.session.post(url, json=payload, timeout=30.0)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def optionsmultiorder(self, strategy, underlying, exchange, expiry_date, legs):
        url = f"{self.host}/api/v1/optionsmultiorder"
        payload = {
            "apikey": self.api_key,
            "strategy": strategy,
            "underlying": underlying,
            "exchange": exchange,
            "expiry_date": expiry_date,
            "legs": legs
        }
        try:
            resp = self.session.post(url, json=payload, timeout=30.0)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

class OptionPositionTracker:
    def __init__(self, sl_pct, tp_pct, max_hold_min):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min

        self.open_legs = []     # List of dicts describing legs
        self.entry_time = None
        self.entry_premium = 0.0 # Total premium collected (or paid)
        self.side = "SELL"       # "SELL" (Credit) or "BUY" (Debit)

    def add_legs(self, legs, entry_prices, side="SELL"):
        """
        legs: list of dicts with keys 'symbol', 'quantity', 'action'
        entry_prices: list of floats corresponding to legs
        side: 'SELL' (Credit strategy) or 'BUY' (Debit strategy)
        """
        self.open_legs = legs
        self.entry_time = datetime.now()
        self.side = side.upper()

        total_prem = 0.0
        for i, leg in enumerate(legs):
            leg['entry_price'] = entry_prices[i]
            # For Credit Strategy: Sell legs add to premium, Buy legs subtract
            # But usually we track "Net Premium" as absolute value for SL/TP calc?
            # Or do we track strictly PnL?
            # Convention: For Credit Strategy, Entry Premium = Sum(Sell Prices) - Sum(Buy Prices)
            #             SL is when Current Cost > Entry Premium * (1 + SL%)

            qty = safe_int(leg.get('quantity', 1))
            price = entry_prices[i]

            if side == "SELL":
                if leg['action'] == "SELL":
                    total_prem += price * qty
                else:
                    total_prem -= price * qty
            else: # BUY
                if leg['action'] == "BUY":
                    total_prem += price * qty
                else:
                    total_prem -= price * qty

        self.entry_premium = total_prem
        logger.info(f"Position Tracked: Side={self.side}, Net Premium={self.entry_premium:.2f}, Time={self.entry_time}")

    def should_exit(self, chain):
        """
        Checks exit conditions based on current chain prices.
        Returns: (bool exit_now, list legs, str reason)
        """
        if not self.open_legs:
            return False, [], ""

        # 1. Time Stop
        if self.max_hold_min > 0:
            elapsed = (datetime.now() - self.entry_time).total_seconds() / 60
            if elapsed >= self.max_hold_min:
                return True, self.open_legs, "time_stop"

        # 2. Calculate Current Value (Cost to Close)
        current_value = 0.0
        missing_price = False

        # Create lookup for LTP
        ltp_map = {}
        for item in chain:
            if item.get("ce", {}).get("symbol"):
                ltp_map[item["ce"]["symbol"]] = safe_float(item["ce"]["ltp"])
            if item.get("pe", {}).get("symbol"):
                ltp_map[item["pe"]["symbol"]] = safe_float(item["pe"]["ltp"])

        for leg in self.open_legs:
            sym = leg["symbol"]
            if sym in ltp_map:
                price = ltp_map[sym]
                qty = safe_int(leg.get("quantity", 1))

                if self.side == "SELL":
                    # To close SELL, we BUY back. Cost is positive.
                    # To close BUY (hedge), we SELL back. Cost is negative (credit).
                    if leg["action"] == "SELL":
                        current_value += price * qty
                    else:
                        current_value -= price * qty
                else: # BUY
                    # To close BUY, we SELL. Value is positive (credit).
                    # To close SELL (hedge), we BUY. Value is negative (debit).
                     if leg["action"] == "BUY":
                        current_value += price * qty
                     else:
                        current_value -= price * qty
            else:
                missing_price = True

        if missing_price:
            return False, [], "missing_data" # Can't calculate PnL accurately

        # 3. Check SL/TP
        # For SELL (Credit):
        #   Profit = Entry Premium - Current Value
        #   Loss if Current Value > Entry Premium
        #   SL Hit if Current Value >= Entry Premium * (1 + SL_PCT/100)
        #   TP Hit if Current Value <= Entry Premium * (1 - TP_PCT/100)

        # For BUY (Debit):
        #   Profit = Current Value - Entry Premium
        #   SL Hit if Current Value <= Entry Premium * (1 - SL_PCT/100)
        #   TP Hit if Current Value >= Entry Premium * (1 + TP_PCT/100)

        if self.side == "SELL":
            # Protective check: if entry premium is very low, SL might be tight.
            # Usually SL is on the premium itself.

            if self.sl_pct > 0 and current_value >= self.entry_premium * (1 + self.sl_pct/100.0):
                return True, self.open_legs, f"stop_loss ({current_value:.2f} vs {self.entry_premium:.2f})"

            if self.tp_pct > 0 and current_value <= self.entry_premium * (1 - self.tp_pct/100.0):
                return True, self.open_legs, f"take_profit ({current_value:.2f} vs {self.entry_premium:.2f})"

        else: # BUY
            if self.sl_pct > 0 and current_value <= self.entry_premium * (1 - self.sl_pct/100.0):
                 return True, self.open_legs, f"stop_loss ({current_value:.2f} vs {self.entry_premium:.2f})"

            if self.tp_pct > 0 and current_value >= self.entry_premium * (1 + self.tp_pct/100.0):
                 return True, self.open_legs, f"take_profit ({current_value:.2f} vs {self.entry_premium:.2f})"

        return False, [], ""

    def clear(self):
        self.open_legs = []
        self.entry_time = None
        self.entry_premium = 0.0
