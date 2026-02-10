import time
import requests
import logging
from datetime import datetime

logger = logging.getLogger("OptionChainUtils")

def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def normalize_expiry(date_str):
    return date_str.upper()

def choose_nearest_expiry(dates):
    """
    Selects the nearest expiry date from a list of DDMMMYY strings.
    Example: ["10FEB26", "13FEB26"] -> "10FEB26"
    """
    if not dates:
        return None

    try:
        # Parse dates
        dt_dates = []
        for d in dates:
            try:
                dt = datetime.strptime(d, "%d%b%y")
                dt_dates.append((d, dt))
            except ValueError:
                continue

        if not dt_dates:
            return dates[0]

        now = datetime.now()
        # Filter future dates (or today)
        future_dates = [x for x in dt_dates if x[1].date() >= now.date()]

        if not future_dates:
            # If all are past, return the last one? Or None?
            # Usually return None or nearest past.
            # But let's assume we want valid expiry.
            # If list is provided, maybe just return the first one if all are past?
            # But sorting by date is safer.
            dt_dates.sort(key=lambda x: x[1])
            return dt_dates[-1][0] if dt_dates else None

        future_dates.sort(key=lambda x: x[1])
        return future_dates[0][0].upper()

    except Exception:
        return dates[0]

def is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False):
    if not chain_resp or chain_resp.get("status") != "success":
        return False, chain_resp.get("message", "Unknown error") if chain_resp else "Empty response"

    chain = chain_resp.get("chain", [])
    if not chain:
        return False, "Empty chain"

    if len(chain) < min_strikes:
        return False, f"Insufficient strikes: {len(chain)} < {min_strikes}"

    # Check middle/ATM strike for validity
    atm_idx = len(chain) // 2
    atm_item = chain[atm_idx]

    if require_oi:
        ce_oi = safe_int(atm_item.get("ce", {}).get("oi", 0))
        pe_oi = safe_int(atm_item.get("pe", {}).get("oi", 0))
        if ce_oi == 0 and pe_oi == 0:
            return False, "Zero OI at ATM"

    if require_volume:
        ce_vol = safe_int(atm_item.get("ce", {}).get("volume", 0))
        pe_vol = safe_int(atm_item.get("pe", {}).get("volume", 0))
        if ce_vol == 0 and pe_vol == 0:
            return False, "Zero Volume at ATM"

    return True, "Valid"

class OptionChainClient:
    def __init__(self, api_key, host):
        self.api_key = api_key
        self.host = host.rstrip("/")

    def expiry(self, underlying, exchange, instrument_type="options"):
        url = f"{self.host}/api/v1/expiry"
        try:
            res = requests.post(url, json={
                "apikey": self.api_key,
                "underlying": underlying,
                "exchange": exchange,
                "type": instrument_type
            }, timeout=10)
            return res.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def optionchain(self, underlying, exchange, expiry_date, strike_count=10):
        url = f"{self.host}/api/v1/optionchain"
        try:
            res = requests.post(url, json={
                "apikey": self.api_key,
                "underlying": underlying,
                "exchange": exchange,
                "expiry": expiry_date,
                "strike_count": strike_count
            }, timeout=10)
            return res.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def optionsmultiorder(self, strategy, underlying, exchange, expiry_date, legs):
        url = f"{self.host}/api/v1/optionsmultiorder"
        try:
            res = requests.post(url, json={
                "apikey": self.api_key,
                "strategy": strategy,
                "underlying": underlying,
                "exchange": exchange,
                "expiry": expiry_date,
                "legs": legs
            }, timeout=10)
            return res.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

class OptionPositionTracker:
    def __init__(self, sl_pct, tp_pct, max_hold_min):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min
        self.open_legs = []
        self.entry_time = None
        self.entry_premium = 0.0
        self.side = "SELL" # Default

    def add_legs(self, legs, entry_prices, side="SELL"):
        """
        Track position legs.
        legs: List of dicts (symbol, quantity, etc.)
        entry_prices: List of floats corresponding to legs
        side: 'SELL' (Credit Strategy) or 'BUY' (Debit Strategy)
        """
        self.open_legs = legs
        self.entry_time = time.time()
        self.entry_premium = sum(entry_prices)
        self.side = side.upper()

    def should_exit(self, chain):
        """
        Check exit conditions based on current chain prices.
        Returns: (bool exit_now, list legs, str reason)
        """
        if not self.open_legs:
            return False, [], ""

        # 1. Time Stop
        if self.max_hold_min > 0:
            elapsed_min = (time.time() - self.entry_time) / 60
            if elapsed_min >= self.max_hold_min:
                return True, self.open_legs, "time_stop"

        # 2. Calculate Current Premium
        current_premium = 0.0
        # Create a lookup map for faster access
        # Key: symbol, Value: ltp
        ltp_map = {}
        for item in chain:
            for otype in ["ce", "pe"]:
                opt = item.get(otype, {})
                if opt.get("symbol"):
                    ltp_map[opt["symbol"]] = safe_float(opt.get("ltp", 0))

        for leg in self.open_legs:
            sym = leg.get("symbol")
            if sym in ltp_map:
                current_premium += ltp_map[sym]
            else:
                # If a leg is missing from chain, we can't calculate PnL accurately.
                # Conservatively, we might want to exit or wait.
                # For now, assume 0 or last known (not tracked here).
                pass

        # 3. PnL Check
        if self.side == "SELL":
            # Credit Strategy: We want premium to go DOWN
            # Profit = Entry - Current
            # Loss = Current - Entry

            # SL: Current > Entry * (1 + SL%)
            sl_threshold = self.entry_premium * (1 + self.sl_pct / 100.0)
            if current_premium >= sl_threshold:
                 return True, self.open_legs, "stop_loss"

            # TP: Current < Entry * (1 - TP%)
            tp_threshold = self.entry_premium * (1 - self.tp_pct / 100.0)
            if current_premium <= tp_threshold:
                 return True, self.open_legs, "take_profit"

        else: # BUY
            # Debit Strategy: We want premium to go UP
            # Profit = Current - Entry
            # Loss = Entry - Current

            # SL: Current < Entry * (1 - SL%)
            sl_threshold = self.entry_premium * (1 - self.sl_pct / 100.0)
            if current_premium <= sl_threshold:
                 return True, self.open_legs, "stop_loss"

            # TP: Current > Entry * (1 + TP%)
            tp_threshold = self.entry_premium * (1 + self.tp_pct / 100.0)
            if current_premium >= tp_threshold:
                 return True, self.open_legs, "take_profit"

        return False, [], ""

    def clear(self):
        self.open_legs = []
        self.entry_time = None
        self.entry_premium = 0.0
