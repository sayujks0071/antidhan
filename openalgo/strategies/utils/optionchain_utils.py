"""
[MOCK] Option Chain Utilities for OpenAlgo Strategies.
This file mocks the behavior of the real utility file for development and testing.
"""
import time
import math
from datetime import datetime

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

def normalize_expiry(expiry_str):
    """Normalize expiry string to DDMMMYY format."""
    # Assuming input is already correct or handles basic normalization
    return expiry_str.upper()

def choose_nearest_expiry(dates):
    """Selects the nearest expiry date from a list."""
    if not dates:
        return None
    # Sort dates based on time difference from now
    # Simplified logic: just pick the first one
    return dates[0]

def is_chain_valid(chain_resp, min_strikes=10, require_oi=True, require_volume=False):
    """Validates the option chain response."""
    if not chain_resp or chain_resp.get("status") != "success":
        return False, "Invalid response status"

    chain = chain_resp.get("chain", [])
    if len(chain) < min_strikes:
        return False, f"Insufficient strikes: {len(chain)} < {min_strikes}"

    return True, "Valid"

class OptionChainClient:
    def __init__(self, api_key, host):
        self.api_key = api_key
        self.host = host

    def expiry(self, underlying, exchange, instrument_type):
        """Mock expiry fetch."""
        # Return a dummy expiry for testing
        return {"status": "success", "data": ["28FEB26", "05MAR26"]}

    def optionchain(self, underlying, exchange, expiry_date, strike_count=10):
        """Mock option chain fetch."""
        # Generate a dummy chain around 24000
        spot = 24000.0
        chain = []
        for i in range(-strike_count, strike_count + 1):
            strike = spot + (i * 50)
            chain.append({
                "strike": strike,
                "ce": {
                    "symbol": f"{underlying}{expiry_date}{int(strike)}CE",
                    "label": "ATM" if i == 0 else (f"OTM{abs(i)}" if i > 0 else f"ITM{abs(i)}"),
                    "ltp": max(100 - (i * 10), 5.0), # Dummy pricing
                    "oi": 100000,
                    "volume": 5000
                },
                "pe": {
                    "symbol": f"{underlying}{expiry_date}{int(strike)}PE",
                    "label": "ATM" if i == 0 else (f"OTM{abs(i)}" if i < 0 else f"ITM{abs(i)}"),
                    "ltp": max(100 + (i * 10), 5.0), # Dummy pricing
                    "oi": 100000,
                    "volume": 5000
                }
            })

        return {
            "status": "success",
            "underlying_ltp": spot,
            "atm_strike": spot,
            "chain": chain
        }

    def optionsmultiorder(self, strategy, underlying, exchange, expiry_date, legs):
        """Mock multi-leg order placement."""
        return {"status": "success", "message": "Order placed successfully (MOCK)", "order_id": "MOCK123"}


class OptionPositionTracker:
    def __init__(self, sl_pct, tp_pct, max_hold_min):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min
        self.open_legs = []
        self.entry_time = None
        self.entry_premium = 0.0 # Total premium collected/paid

    def add_legs(self, legs, entry_prices, side="SELL"):
        """
        Tracks a new position.
        legs: List of leg dictionaries (symbol, quantity, action, product)
        entry_prices: List of entry prices corresponding to legs
        side: "SELL" (Credit) or "BUY" (Debit) - determines PnL logic
        """
        self.open_legs = legs
        self.entry_time = time.time()
        self.side = side

        # Calculate total premium
        self.entry_premium = sum([p * l.get('quantity', 1) for p, l in zip(entry_prices, legs)])
        # Adjust for side? Usually just track total premium value.
        # If side is SELL, we collected premium. PnL = Entry - Current.
        # If side is BUY, we paid premium. PnL = Current - Entry.

        # For simplicity in mock, just store the premium sum
        self.entry_prices = entry_prices

    def should_exit(self, chain):
        """
        Checks exit conditions based on current chain prices.
        Returns: (bool, legs_to_exit, reason)
        """
        if not self.open_legs:
            return False, [], ""

        # Check Time Stop
        elapsed_min = (time.time() - self.entry_time) / 60
        if elapsed_min >= self.max_hold_min:
            return True, self.open_legs, "time_stop"

        # Calculate Current Premium
        current_premium = 0.0
        # Find LTP for each leg in chain
        # Ideally, we map symbols. For mock, we just assume prices moved slightly against us
        # to trigger SL or for us to trigger TP.

        # Let's just simulate random fluctuation or stable prices
        # In a real implementation, we would look up symbols in the chain

        # For now, return False unless time stop
        return False, [], ""

    def clear(self):
        """Clears the tracked position."""
        self.open_legs = []
        self.entry_time = None
        self.entry_premium = 0.0
