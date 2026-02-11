#!/usr/bin/env python3
"""
NiftyIronCondor - NIFTY Options (OpenAlgo Web UI Compatible)
Sell OTM2, Buy OTM4 wings, enter >10AM, SL 40%, TP 50%
"""
import os
import sys
import time
from datetime import datetime, timedelta

# Line-buffered output (required for real-time log capture)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
sys.path.insert(0, utils_dir)

try:
    from trading_utils import is_market_open
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
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)

# API Key retrieval (MANDATORY - place after configuration section)
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

class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Strategy Parameters
        self.otm_sell_offset = int(os.getenv("OTM_SELL_OFFSET", "2")) # Sell OTM2
        self.otm_buy_offset = int(os.getenv("OTM_BUY_OFFSET", "4"))   # Buy OTM4
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))

        self.sl_pct = float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # Risk Management
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=int(os.getenv("MAX_ORDERS_PER_DAY", "1")),
            max_per_hour=int(os.getenv("MAX_ORDERS_PER_HOUR", "1")),
            cooldown_seconds=int(os.getenv("COOLDOWN_SECONDS", "300"))
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_check = 0
        self.entered_today = False # Explicit one-per-day flag if limiter resets

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            self.logger.info("Refreshing expiry dates...")
            res = self.client.expiry(self.underlying, self.options_exchange)
            if res.get("status") == "success":
                dates = res.get("data", [])
                self.expiry = choose_nearest_expiry(dates)
                self.logger.info(f"Selected Expiry: {self.expiry}")
                self.last_expiry_check = now
            else:
                self.logger.error(f"Failed to fetch expiry: {res}")

    def get_legs_from_chain(self, chain):
        """Identify OTM2 and OTM4 strikes relative to ATM."""
        # Find ATM
        atm_idx = -1
        for i, item in enumerate(chain):
            if item.get("ce", {}).get("label") == "ATM":
                atm_idx = i
                break

        if atm_idx == -1:
            return None, "ATM not found"

        # Ensure we have enough strikes
        if atm_idx - self.otm_buy_offset < 0 or atm_idx + self.otm_buy_offset >= len(chain):
            return None, "Not enough strikes for OTM offsets"

        # Sell OTM2
        # CE OTM is higher strike (index + offset)
        # PE OTM is lower strike (index - offset)
        sell_ce_item = chain[atm_idx + self.otm_sell_offset]
        sell_pe_item = chain[atm_idx - self.otm_sell_offset]

        # Buy OTM4
        buy_ce_item = chain[atm_idx + self.otm_buy_offset]
        buy_pe_item = chain[atm_idx - self.otm_buy_offset]

        legs = []
        # Buy Wings First (Margin Benefit)
        legs.append({
            "symbol": buy_ce_item["ce"]["symbol"],
            "action": "BUY",
            "option_type": "CE",
            "offset": f"OTM{self.otm_buy_offset}",
            "ltp": safe_float(buy_ce_item["ce"].get("ltp"))
        })
        legs.append({
            "symbol": buy_pe_item["pe"]["symbol"],
            "action": "BUY",
            "option_type": "PE",
            "offset": f"OTM{self.otm_buy_offset}",
            "ltp": safe_float(buy_pe_item["pe"].get("ltp"))
        })

        # Sell Body
        legs.append({
            "symbol": sell_ce_item["ce"]["symbol"],
            "action": "SELL",
            "option_type": "CE",
            "offset": f"OTM{self.otm_sell_offset}",
            "ltp": safe_float(sell_ce_item["ce"].get("ltp"))
        })
        legs.append({
            "symbol": sell_pe_item["pe"]["symbol"],
            "action": "SELL",
            "option_type": "PE",
            "offset": f"OTM{self.otm_sell_offset}",
            "ltp": safe_float(sell_pe_item["pe"].get("ltp"))
        })

        return legs, "OK"

    def can_trade(self):
        # Time Filters
        now = datetime.now()
        if now.hour < 10: # Don't trade before 10 AM
            return False
        if now.hour > 14 or (now.hour == 14 and now.minute >= 30): # Don't enter after 2:30 PM
            return False

        if not self.limiter.allow():
            return False

        return True

    def _close_position(self, chain, reason):
        self.logger.info(f"Exiting position. Reason: {reason}")

        # We need to construct opposite orders for open legs
        exit_legs = []
        entry_prices = [] # Not used for exit order but tracking

        # Priority: Buy back Shorts first (to cover risk), then Sell Longs

        closure_orders = []
        for leg in self.tracker.open_legs:
            original_action = leg["action"]
            exit_action = "BUY" if original_action == "SELL" else "SELL"

            closure_orders.append({
                "symbol": leg["symbol"],
                "action": exit_action,
                "quantity": leg.get("quantity", self.quantity),
                "product": self.product,
                "original_action": original_action
            })

        # Sort: BUY actions first
        closure_orders.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        for order in closure_orders:
            try:
                # Use APIClient for single orders (exit)
                from trading_utils import APIClient
                api_client = APIClient(API_KEY, HOST)

                res = api_client.placesmartorder(
                    strategy="NiftyIronCondor",
                    symbol=order["symbol"],
                    action=order["action"],
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=order["product"],
                    quantity=order["quantity"],
                    position_size=order["quantity"]
                )
                self.logger.info(f"Exit Order {order['symbol']} {order['action']}: {res}")
                time.sleep(0.5) # Avoid rate limits

            except Exception as e:
                self.logger.error(f"Exit failed for {order['symbol']}: {e}")

        self.tracker.clear()
        self.logger.info("Position closed and tracker cleared.")

    def run(self):
        self.logger.info(f"Strategy {os.path.basename(__file__)} starting...")
        self.logger.info(format_kv(event="start", underlying=self.underlying, sl=self.sl_pct, tp=self.tp_pct))

        while True:
            try:
                # 1. Market Hours Check
                if not is_market_open():
                    self.logger.info("Market is closed. Sleeping...")
                    time.sleep(60)
                    continue

                # 2. Expiry Management
                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No expiry found. Sleeping...")
                    time.sleep(self.sleep_seconds)
                    continue

                # 3. Get Data
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=True)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = chain_resp.get("underlying_ltp", 0)

                # 4. Exit Management (Monitor existing positions)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self.logger.info(format_kv(event="signal_exit", reason=exit_reason))
                        self._close_position(chain, exit_reason)

                    # EOD Check (3:15 PM)
                    now = datetime.now()
                    if now.hour == 15 and now.minute >= 15:
                        self.logger.info("EOD Auto-squareoff triggered.")
                        self._close_position(chain, "eod_sqoff")

                    time.sleep(self.sleep_seconds)
                    continue

                # 5. Entry Logic
                if self.can_trade():
                    # Calculate Straddle Premium
                    atm_item = None
                    for item in chain:
                        if item.get("ce", {}).get("label") == "ATM":
                            atm_item = item
                            break

                    if atm_item:
                        ce_ltp = safe_float(atm_item["ce"].get("ltp"))
                        pe_ltp = safe_float(atm_item["pe"].get("ltp"))
                        straddle_prem = ce_ltp + pe_ltp

                        self.logger.info(format_kv(
                            spot=underlying_ltp,
                            straddle=f"{straddle_prem:.2f}",
                            threshold=self.min_straddle_premium
                        ))

                        if straddle_prem > self.min_straddle_premium:
                            # Construct Legs
                            legs, msg = self.get_legs_from_chain(chain)
                            if legs:
                                self.logger.info(f"Entry Signal: Iron Condor. Legs: {len(legs)}")

                                api_legs = []
                                tracker_legs = []
                                tracker_prices = []

                                for leg in legs:
                                    api_legs.append({
                                        "symbol": leg["symbol"],
                                        "action": leg["action"],
                                        "option_type": leg["option_type"],
                                        "quantity": self.quantity,
                                        "product": self.product
                                    })
                                    tracker_legs.append({
                                        "symbol": leg["symbol"],
                                        "action": leg["action"],
                                        "quantity": self.quantity
                                    })
                                    tracker_prices.append(leg["ltp"])

                                # Place Order
                                self.logger.info("Placing Multi-leg Order...")
                                res = self.client.optionsmultiorder(
                                    strategy="NiftyIronCondor",
                                    underlying=self.underlying,
                                    exchange=self.options_exchange,
                                    expiry_date=self.expiry,
                                    legs=api_legs
                                )

                                if res.get("status") == "success":
                                    self.logger.info(format_kv(event="trade", status="success", order_id=res.get("order_id")))
                                    self.tracker.add_legs(tracker_legs, tracker_prices, side="SELL")
                                    self.limiter.record()
                                else:
                                    self.logger.error(f"Order failed: {res}")
                            else:
                                self.logger.warning(f"Could not calculate legs: {msg}")
                        else:
                            pass # Premium too low
                    else:
                        self.logger.warning("ATM strike not found.")

            except Exception as e:
                self.logger.error(f"Strategy Loop Error: {e}", exc_info=True)
                time.sleep(5)

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    strategy = NiftyIronCondorStrategy()
    strategy.run()
