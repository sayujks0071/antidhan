import logging
import time
from datetime import datetime, timedelta
import math
from trading_utils import APIClient, httpx_client

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

def normalize_expiry(date_str):
    """
    Normalizes expiry date string to ensure format consistency.
    """
    # Placeholder for more complex logic if needed
    return date_str

def is_chain_valid(chain_resp, min_strikes=8):
    """
    Validates the option chain response.
    """
    if not chain_resp or chain_resp.get("status") != "success":
        return False, "API Error or Empty Response"

    chain = chain_resp.get("chain", [])
    if not chain:
        return False, "Empty Chain"

    if len(chain) < min_strikes:
        return False, f"Insufficient Strikes: {len(chain)} < {min_strikes}"

    return True, "Valid"

def choose_nearest_expiry(expiry_dates):
    """
    Selects the nearest expiry date from a list of date strings.
    Expects dates in "YYYY-MM-DD" or "DD-MMM-YYYY" format.
    """
    if not expiry_dates:
        return None

    # Sort dates
    try:
        # Try parsing as YYYY-MM-DD
        dates = sorted(expiry_dates, key=lambda x: datetime.strptime(x, "%Y-%m-%d"))
    except ValueError:
        try:
            # Try parsing as DD-MMM-YYYY
            dates = sorted(expiry_dates, key=lambda x: datetime.strptime(x, "%d-%b-%Y"))
        except ValueError:
            # Fallback to string sort
            dates = sorted(expiry_dates)

    # Return the first one (nearest)
    return dates[0]

def choose_nearest_monthly_expiry(expiry_dates):
    """
    Selects the nearest *monthly* expiry date.
    Assumes monthly expiries are the last expiry of the month.
    """
    if not expiry_dates:
        return None

    # Parse dates
    parsed_dates = []
    for d_str in expiry_dates:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d")
            parsed_dates.append(d)
        except ValueError:
            try:
                d = datetime.strptime(d_str, "%d-%b-%Y")
                parsed_dates.append(d)
            except ValueError:
                continue

    parsed_dates.sort()

    if not parsed_dates:
        return None

    # Group by (Year, Month)
    by_month = {}
    for d in parsed_dates:
        key = (d.year, d.month)
        if key not in by_month:
            by_month[key] = []
        by_month[key].append(d)

    # Identify monthly expiries (last date in each month group)
    monthly_expiries = []
    for key in sorted(by_month.keys()):
        dates_in_month = by_month[key]
        monthly_expiries.append(dates_in_month[-1])

    # Find the first monthly expiry that is today or in the future
    now = datetime.now()
    # Normalize now to date only for comparison
    today = datetime(now.year, now.month, now.day)

    for d in monthly_expiries:
        if d >= today:
            # Return in original format if possible, but we parsed it.
            # We need to find the original string.
            # This is a bit tricky if formats mixed.
            # We'll just return YYYY-MM-DD as standard.
            return d.strftime("%Y-%m-%d")

    return None


class OptionChainClient(APIClient):
    """
    Client for Option Chain specific operations.
    Inherits from APIClient to reuse connection logic.
    """
    def __init__(self, api_key, host="http://127.0.0.1:5000"):
        super().__init__(api_key, host)

    def expiry(self, underlying, exchange, instrument_type="options"):
        """
        Fetches expiry dates for the given underlying.
        """
        url = f"{self.host}/api/v1/expiry"
        payload = {
            "underlying": underlying,
            "exchange": exchange,
            "instrument_type": instrument_type,
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
        """
        Fetches option chain and enriches it with labels (ATM, OTM1, etc.).
        """
        # We can use the parent's get_option_chain but we need to match the signature and return format expected by strategy
        # Strategy expects: {"status": "success", "chain": [...]}
        # Parent get_option_chain returns data['data'] which is the list of dicts.

        # We need to reimplement or wrap to add labels.
        # Let's call the API endpoint directly to ensure we get raw data then process.

        url = f"{self.host}/api/v1/optionchain"
        payload = {
            "symbol": underlying,
            "exchange": exchange,
            "expiry": expiry_date,
            "count": strike_count,
            "apikey": self.api_key
        }

        try:
            response = httpx_client.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                return {"status": "error", "message": f"HTTP {response.status_code}"}

            data = response.json()
            if data.get("status") != "success":
                return data

            chain_data = data.get("data", [])

            # Enrich with labels
            # Find ATM
            # Assuming chain is sorted by strike? Usually it is.
            # If not, sort it.
            chain_data.sort(key=lambda x: safe_float(x.get("strike", 0)))

            # Find spot price from the first item or separate call
            # Usually option chain response includes spot price or we infer from ATM.
            # Let's infer ATM from minimium difference between strike and spot if available.
            # If spot not in response, we have to guess or use the middle.

            # If the API is "smart", it might already label ATM.
            # Strategy checks: if item.get("ce", {}).get("label") == "ATM":

            # Let's add labels if missing.
            # We need the spot price.
            spot_price = 0
            # Check if any item has underlying_price
            if chain_data:
                spot_price = chain_data[0].get("underlying_price", 0)

            if spot_price:
                # Calculate distances
                deltas = [(i, abs(safe_float(item["strike"]) - spot_price)) for i, item in enumerate(chain_data)]
                # Find min distance index
                atm_index = min(deltas, key=lambda x: x[1])[0]

                # Assign labels
                for i, item in enumerate(chain_data):
                    offset = i - atm_index
                    label = "ATM" if offset == 0 else f"OTM{abs(offset)}" if offset != 0 else "ATM" # Logic for CE/PE differs

                    # For CE: higher strike is OTM
                    # For PE: lower strike is OTM

                    # But the strategy uses "OTM2" and looks for it in CE and PE separately?
                    # "OTM2 CE means finding label="OTM2" in CE dict"

                    ce = item.get("ce", {})
                    pe = item.get("pe", {})

                    if offset == 0:
                        ce["label"] = "ATM"
                        pe["label"] = "ATM"
                    elif offset > 0: # Higher strike
                        ce["label"] = f"OTM{offset}" # OTM for Call
                        pe["label"] = f"ITM{offset}" # ITM for Put
                    else: # Lower strike (offset < 0)
                        ce["label"] = f"ITM{abs(offset)}" # ITM for Call
                        pe["label"] = f"OTM{abs(offset)}" # OTM for Put

                    item["ce"] = ce
                    item["pe"] = pe

            return {"status": "success", "chain": chain_data}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def optionsmultiorder(self, strategy, underlying, exchange, expiry_date, legs):
        """
        Places multiple option orders.
        """
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
    """
    Tracks open option positions and manages exits.
    """
    def __init__(self, sl_pct=0.0, tp_pct=0.0, max_hold_min=0):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min
        self.open_legs = []
        self.entry_time = None
        self.side = "NEUTRAL" # LONG or SELL (Credit)

    def add_legs(self, legs, entry_prices, side="SELL"):
        """
        Adds legs to the tracker.
        legs: list of dicts with keys (symbol, quantity, product, action)
        entry_prices: list of floats matching legs
        """
        self.open_legs = []
        for i, leg in enumerate(legs):
            leg_copy = leg.copy()
            leg_copy["entry_price"] = entry_prices[i]
            self.open_legs.append(leg_copy)

        self.entry_time = time.time()
        self.side = side

    def should_exit(self, chain):
        """
        Checks if positions should be exited based on SL/TP or time.
        Returns: (bool, legs_to_close, reason)
        """
        if not self.open_legs:
            return False, [], ""

        # Time Check
        if self.max_hold_min > 0:
            if time.time() - self.entry_time > self.max_hold_min * 60:
                return True, self.open_legs, "Max Hold Time Reached"

        # PnL Check
        # We need current LTPs for open legs.
        # We can find them in the chain passed in.

        total_pnl = 0.0
        total_premium = 0.0
        current_premium = 0.0

        # Build a map of symbol -> ltp from chain
        symbol_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): symbol_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): symbol_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        # Calculate PnL
        for leg in self.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            qty = leg["quantity"]
            action = leg["action"] # BUY or SELL

            ltp = symbol_map.get(sym, entry) # Fallback to entry if not found (no PnL change)

            if action == "BUY":
                pnl = (ltp - entry) * qty
                total_premium += entry * qty # Cost
                current_premium += ltp * qty
            else: # SELL
                pnl = (entry - ltp) * qty
                total_premium += entry * qty # Credit received
                current_premium += ltp * qty # Cost to close

            total_pnl += pnl

        # Calculate PnL Percentage based on premium
        # For Credit strategies (Iron Condor), we track premium collected.
        # If premium increases (current_premium > total_premium), we are losing.
        # If premium decreases, we are winning.

        # SL/TP logic for defined risk strategies often looks at total premium collected.
        # SL: Premium expands by X%
        # TP: Premium decays by Y%

        if self.side == "SELL":
            # Net Credit Strategy
            initial_credit = total_premium # Approximate (ignoring buy legs cost for now, or total_premium is net?)
            # Actually total_premium above sums everything positive.
            # Let's re-calculate net credit properly if we mixed buys and sells.

            # Iron Condor: Sell OTM2, Buy OTM4.
            # Net Credit = (Sell Price - Buy Price)
            # Strategy passes all legs.

            net_entry = 0.0
            net_current = 0.0

            for leg in self.open_legs:
                sym = leg["symbol"]
                entry = leg["entry_price"]
                ltp = symbol_map.get(sym, entry)
                qty = leg["quantity"]

                if leg["action"] == "SELL":
                    net_entry += entry * qty
                    net_current += ltp * qty
                else:
                    net_entry -= entry * qty
                    net_current -= ltp * qty

            # For Credit strategy:
            # PnL = Net Entry (Credit) - Net Current (Debit to close)
            pnl = net_entry - net_current

            # SL: PnL < - (SL_PCT * Net Entry)
            if self.sl_pct > 0 and pnl < -(self.sl_pct / 100.0) * net_entry:
                return True, self.open_legs, f"SL Hit: PnL {pnl:.2f} < -{self.sl_pct}% of {net_entry:.2f}"

            # TP: PnL > (TP_PCT * Net Entry)
            if self.tp_pct > 0 and pnl > (self.tp_pct / 100.0) * net_entry:
                return True, self.open_legs, f"TP Hit: PnL {pnl:.2f} > {self.tp_pct}% of {net_entry:.2f}"

        return False, [], ""

    def clear(self):
        self.open_legs = []
        self.entry_time = None
