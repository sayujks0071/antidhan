#!/usr/bin/env python3
"""
[Nifty Adaptive Iron Condor] - NIFTY Options (OpenAlgo Web UI Compatible)
Smart Nifty Iron Condor with PCR Filter and Net Credit Risk Management.
Logic:
- Entry: > 10:00 AM, if ATM Straddle Premium > 100 AND PCR is Neutral (0.8 - 1.2).
- Setup: Sell OTM2 Strangle + Buy OTM4 Wings (Iron Condor).
- Risk: SL 40% of Net Credit, TP 50% of Net Credit.
- Management: Max Hold 45 mins, 1 Trade/Day, EOD Exit 3:15 PM.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# Line-buffered output (required for real-time log capture)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)

# Robustly find the correct utils directory (avoiding openalgo/utils which shadows logging)
possible_utils_paths = [
    os.path.join(script_dir, "utils"),                                   # If inside strategies/
    os.path.join(os.path.dirname(script_dir), "utils"),                  # If inside strategies/subdir
    os.path.join(os.path.dirname(script_dir), "strategies", "utils"),    # From root
]

utils_path_found = False
for p in possible_utils_paths:
    if os.path.isdir(p) and os.path.exists(os.path.join(p, "optionchain_utils.py")):
        sys.path.insert(0, p)
        utils_path_found = True
        break

if not utils_path_found:
    print("Warning: Could not find strategy utils directory with optionchain_utils.py", flush=True)
    # Fallback to standard prompt boilerplate assumption if search fails
    sys.path.insert(0, os.path.join(os.path.dirname(script_dir), "utils"))

try:
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        normalize_expiry,
        safe_float,
        safe_int,
    )
    from strategy_common import SignalDebouncer, TradeLedger, TradeLimiter, format_kv
except ImportError as e:
    print(f"ERROR: Could not import strategy utilities: {e}", flush=True)
    sys.exit(1)

# Robust Market Open Check (Local Fallback to avoid dependencies)
try:
    from trading_utils import is_market_open
except ImportError:
    print("Warning: trading_utils import failed. Using local is_market_open fallback.", flush=True)
    def is_market_open():
        """Check if market is open (09:15 - 15:30 IST)."""
        # IST is UTC+5:30
        ist_offset = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist_offset)

        # Check weekend (5=Saturday, 6=Sunday)
        if now.weekday() >= 5:
            return False

        current_time = now.time()
        start_time = datetime.strptime("09:15", "%H:%M").time()
        end_time = datetime.strptime("15:30", "%H:%M").time()

        return start_time <= current_time <= end_time


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# API Key retrieval
API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

if not API_KEY:
    try:
        from database.auth_db import get_first_available_api_key
        API_KEY = get_first_available_api_key()
        if API_KEY:
            print("Successfully retrieved API Key from database.", flush=True)
    except Exception as e:
        print(f"Warning: Could not retrieve API key from database: {e}", flush=True)

if not API_KEY:
    raise ValueError("API Key must be set in OPENALGO_APIKEY environment variable")


# ===========================
# CONFIGURATION
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyAdaptiveIronCondor")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

# Strategy Parameters
SELL_OFFSET = os.getenv("SELL_OFFSET", "OTM2")
BUY_OFFSET = os.getenv("BUY_OFFSET", "OTM4")
MIN_STRADDLE_PREMIUM = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "100.0"))
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "10:00")

# PCR Filter Parameters
PCR_MIN = safe_float(os.getenv("PCR_MIN", "0.8"))
PCR_MAX = safe_float(os.getenv("PCR_MAX", "1.2"))

# Risk Parameters (Percentage of NET CREDIT)
SL_PCT = safe_float(os.getenv("SL_PCT", "40.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

# Rate Limiting
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Manual Expiry Override
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()


class NetCreditPositionTracker(OptionPositionTracker):
    """
    Custom Position Tracker for Credit Strategies (e.g. Iron Condor).
    Calculates PnL based on Net Credit Collected, not Gross Premium Traded.
    """
    def should_exit(self, chain):
        if not self.open_legs:
            return False, [], ""

        # 1. Time Stop
        if self.entry_time:
            minutes_held = (datetime.now() - self.entry_time).total_seconds() / 60
            if minutes_held >= self.max_hold_min:
                return True, self.open_legs, f"time_stop ({int(minutes_held)}m)"

        # 2. Net Credit PnL Check
        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        net_credit_collected = 0.0
        current_cost_to_close = 0.0

        for leg in self.open_legs:
            sym = leg["symbol"]
            entry = leg["entry_price"]
            curr = ltp_map.get(sym, entry) # Fallback to entry
            action = leg["action"].upper()
            qty = safe_int(leg.get("quantity", 1))

            if action == "SELL":
                net_credit_collected += (entry * qty)
                current_cost_to_close += (curr * qty)
            else: # BUY
                net_credit_collected -= (entry * qty)
                current_cost_to_close -= (curr * qty)

        # Avoid division by zero
        if abs(net_credit_collected) < 0.01:
            return False, [], ""

        # PnL = (Net Credit Collected) - (Cost to Close)
        # Positive PnL means we kept more credit than it costs to close.
        pnl = net_credit_collected - current_cost_to_close

        # PnL % relative to MAX POTENTIAL PROFIT (Net Credit)
        pnl_pct = (pnl / abs(net_credit_collected)) * 100

        # Check SL (e.g. -40%)
        if pnl_pct <= -self.sl_pct:
            return True, self.open_legs, f"stop_loss ({pnl_pct:.1f}%)"

        # Check TP (e.g. +50%)
        if pnl_pct >= self.tp_pct:
            return True, self.open_legs, f"take_profit ({pnl_pct:.1f}%)"

        return False, [], ""


class NiftyAdaptiveIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        # Use Custom Tracker for Net Credit PnL
        self.tracker = NetCreditPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.expiry = EXPIRY_DATE
        self.last_expiry_check = 0
        self.entered_today = False
        self.current_date = datetime.now().date()

    def ensure_expiry(self):
        """Refresh expiry date if needed."""
        if self.expiry and (time.time() - self.last_expiry_check < EXPIRY_REFRESH_SEC):
            return

        self.logger.info("Fetching available expiry dates...")
        try:
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.last_expiry_check = time.time()
                    self.logger.info(f"Selected expiry: {self.expiry}")
                else:
                    self.logger.warning("No valid future expiry found.")
            else:
                self.logger.error(f"Failed to fetch expiry: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Expiry fetch error: {e}")

    def _calculate_pcr(self, chain):
        """Calculate Put-Call Ratio (Total Put OI / Total Call OI)."""
        total_ce_oi = 0
        total_pe_oi = 0

        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            total_ce_oi += safe_int(ce.get("oi"))
            total_pe_oi += safe_int(pe.get("oi"))

        if total_ce_oi == 0:
            return 0.0

        return total_pe_oi / total_ce_oi

    def _close_position(self, chain, reason):
        """Close all open legs."""
        self.logger.info(f"Closing position. Reason: {reason}")

        if not self.tracker.open_legs:
            return

        # Prepare exit legs (Reverse actions)
        legs_to_close = []
        for leg in self.tracker.open_legs:
            close_leg = {
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": "BUY" if leg["action"] == "SELL" else "SELL",
                "quantity": leg["quantity"],
                "product": leg.get("product", PRODUCT)
            }
            legs_to_close.append(close_leg)

        # Sort: BUY actions (closing shorts) first for margin safety
        legs_to_close.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=legs_to_close
            )
            self.logger.info(f"Exit Order Response: {res}")

            if res.get("status") == "success":
                self.tracker.clear()
            else:
                self.logger.error(f"Exit failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _open_position(self, chain, entry_reason):
        """Open Iron Condor Position."""
        self.logger.info(f"Attempting to open Iron Condor ({entry_reason})...")

        # Define legs based on offsets
        legs_config = [
            {"offset": BUY_OFFSET, "option_type": "CE", "action": "BUY"},   # Wings (Protection)
            {"offset": BUY_OFFSET, "option_type": "PE", "action": "BUY"},
            {"offset": SELL_OFFSET, "option_type": "CE", "action": "SELL"}, # Body (Credit)
            {"offset": SELL_OFFSET, "option_type": "PE", "action": "SELL"},
        ]

        resolved_legs = []
        api_legs = []

        # Resolve symbols and LTPs
        for cfg in legs_config:
            offset = cfg["offset"]
            otype = cfg["option_type"].lower()

            found_item = None
            for item in chain:
                opt = item.get(otype, {})
                if opt.get("label") == offset:
                    found_item = opt
                    break

            if found_item:
                symbol = found_item.get("symbol")
                ltp = safe_float(found_item.get("ltp"))

                api_legs.append({
                    "offset": offset,
                    "option_type": cfg["option_type"],
                    "action": cfg["action"],
                    "quantity": QUANTITY,
                    "product": PRODUCT
                })

                resolved_legs.append({
                    "symbol": symbol,
                    "option_type": cfg["option_type"],
                    "action": cfg["action"],
                    "quantity": QUANTITY,
                    "entry_price": ltp,
                    "product": PRODUCT
                })
            else:
                self.logger.warning(f"Could not resolve {offset} {cfg['option_type']}")
                return

        if len(resolved_legs) != 4:
            self.logger.error("Failed to resolve all 4 legs.")
            return

        # Sort API legs: BUY first
        api_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=api_legs
            )

            if res.get("status") == "success":
                self.logger.info(f"Entry Order Success: {res}")

                # Add to Tracker
                entry_prices = [leg["entry_price"] for leg in resolved_legs]
                self.tracker.add_legs(resolved_legs, entry_prices, side="SELL") # Iron Condor is Credit strategy

                self.entered_today = True
                self.limiter.record()
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # 0. Daily Reset
                if datetime.now().date() != self.current_date:
                    self.entered_today = False
                    self.current_date = datetime.now().date()

                # 1. Market Hours Check
                if not is_market_open():
                    time.sleep(60)
                    continue

                # 2. Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No expiry available.")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch Data
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT,
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=STRIKE_COUNT)
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # 4. Exit Management (Priority)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Exit (3:15 PM)
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    eod_time = datetime.strptime("15:15", "%H:%M").time()

                    if now.time() >= eod_time:
                        exit_now = True
                        exit_reason = "eod_sqoff"

                    if exit_now:
                        self.logger.info(f"Exit Signal: {exit_reason}")
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue
                    else:
                         self.logger.info(format_kv(
                            spot=f"{underlying_ltp:.2f}",
                            pos="OPEN",
                            expiry=self.expiry
                        ))

                # 5. Entry Logic
                if not self.tracker.open_legs and not self.entered_today:

                    # Time Check
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    start_time_dt = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
                    end_time_dt = datetime.strptime("14:30", "%H:%M").time()

                    if start_time_dt <= now.time() <= end_time_dt:

                        if self.limiter.allow():
                            # Logic: Straddle Premium > Threshold AND PCR Neutral
                            atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)

                            pcr = self._calculate_pcr(chain)

                            if atm_item:
                                ce_ltp = safe_float((atm_item.get("ce") or {}).get("ltp"))
                                pe_ltp = safe_float((atm_item.get("pe") or {}).get("ltp"))
                                straddle_premium = ce_ltp + pe_ltp

                                self.logger.info(format_kv(
                                    spot=f"{underlying_ltp:.2f}",
                                    straddle=f"{straddle_premium:.2f}",
                                    pcr=f"{pcr:.2f}",
                                    pos="FLAT",
                                    expiry=self.expiry
                                ))

                                should_enter = (straddle_premium > MIN_STRADDLE_PREMIUM) and (PCR_MIN <= pcr <= PCR_MAX)

                                if self.debouncer.edge("entry_signal", should_enter):
                                    entry_reason = f"straddle_{straddle_premium:.2f}_gt_{MIN_STRADDLE_PREMIUM}_pcr_{pcr:.2f}"
                                    self._open_position(chain, entry_reason)
                    else:
                        # Outside entry window, just log occasionally
                        pass

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftyAdaptiveIronCondor()
    strategy.run()
