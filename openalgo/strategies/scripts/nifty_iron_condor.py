#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM (premium > 120), sells OTM2/buys OTM4, 40% SL/50% TP, 45 min max hold.
"""
import os
import sys
import time
from datetime import datetime

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


class NiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Strategy Parameters
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.exchange_underlying = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.exchange_options = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Parameters
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Time Constraints
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # Trade Limits
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )

        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.debouncer = SignalDebouncer()

        # State
        self.expiry = None
        self.last_expiry_refresh = 0
        self.long_legs = [] # Store long legs separately for closing

        self.logger.info(f"Initialized {self.strategy_name} - SL: {self.sl_pct}%, TP: {self.tp_pct}%, MaxHold: {self.max_hold_min}m")

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            res = self.client.expiry(self.underlying, self.exchange_options, "options")
            if res.get("status") == "success" and res.get("data"):
                dates = res["data"]
                self.expiry = choose_nearest_expiry(dates)
                if self.expiry:
                    self.last_expiry_refresh = now
                    self.logger.info(f"Selected Expiry: {self.expiry}")
                else:
                    self.logger.warning("Could not resolve valid expiry date")
            else:
                self.logger.warning(f"Failed to fetch expiry dates: {res}")

    def can_trade_time(self):
        # Enters after 10 AM, exits all positions by 3:15 PM
        now = datetime.now()
        current_time = now.time()

        if current_time < datetime.strptime("10:00", "%H:%M").time():
            return False
        if current_time >= datetime.strptime("14:30", "%H:%M").time(): # stop entering before 3PM
            return False

        return True

    def should_eod_squareoff(self):
        now = datetime.now()
        current_time = now.time()
        eod_time = datetime.strptime("15:15", "%H:%M").time()
        return current_time >= eod_time

    def get_atm_strike(self, chain):
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                return item["strike"]
        return None

    def calculate_straddle_premium(self, chain, atm_strike):
        ce_ltp = 0.0
        pe_ltp = 0.0
        for item in chain:
            if item["strike"] == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                break
        return ce_ltp + pe_ltp

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position: {reason}")

        # Close tracked short legs
        if self.tracker.open_legs:
            legs_to_close = []
            for leg in self.tracker.open_legs:
                close_action = "BUY" if leg["action"] == "SELL" else "SELL"
                # If we need exact option symbols
                sym = leg.get("symbol")
                if sym:
                    legs_to_close.append({
                        "symbol": sym,
                        "action": close_action,
                        "quantity": leg["quantity"]
                    })

            for leg in legs_to_close:
                # Use placesmartorder directly for individual legs using symbols
                self.logger.info(f"Closing Short Leg: {leg['action']} {leg['quantity']} {leg['symbol']}")
                try:
                    import trading_utils
                    client_tu = trading_utils.APIClient(api_key=API_KEY, host=HOST)
                    client_tu.placesmartorder(
                        strategy=self.strategy_name,
                        symbol=leg['symbol'],
                        action=leg['action'],
                        exchange=self.exchange_options,
                        pricetype="MARKET",
                        product=self.product,
                        quantity=leg['quantity'],
                        position_size=leg['quantity']
                    )
                except Exception as e:
                    self.logger.error(f"Failed to close leg {leg['symbol']}: {e}")

        # Close untracked long legs
        if self.long_legs:
            for leg in self.long_legs:
                close_action = "SELL" if leg["action"] == "BUY" else "BUY"
                sym = leg.get("symbol")
                if sym:
                    self.logger.info(f"Closing Long Leg: {close_action} {leg['quantity']} {sym}")
                    try:
                        import trading_utils
                        client_tu = trading_utils.APIClient(api_key=API_KEY, host=HOST)
                        client_tu.placesmartorder(
                            strategy=self.strategy_name,
                            symbol=sym,
                            action=close_action,
                            exchange=self.exchange_options,
                            pricetype="MARKET",
                            product=self.product,
                            quantity=leg['quantity'],
                            position_size=leg['quantity']
                        )
                    except Exception as e:
                        self.logger.error(f"Failed to close leg {sym}: {e}")

        self.tracker.clear()
        self.long_legs = []

    def execute_entry(self, chain_resp, chain):
        # Iron Condor multi-leg setup
        # Sells OTM2 CE and PE, buys OTM4 CE and PE

        legs_def = [
            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
        ]

        self.logger.info(f"event=trade action=ENTER strategy={self.strategy_name} offset_sell=OTM2 offset_buy=OTM4")

        resp = self.client.optionsmultiorder(
            strategy=self.strategy_name,
            underlying=self.underlying,
            exchange=self.exchange_options,
            expiry_date=self.expiry,
            legs=legs_def
        )

        self.logger.info(f"Trade response: {resp}")

        # Find exact symbols and entry prices from the chain
        # so we can track them in OptionPositionTracker
        atm_strike = chain_resp.get("atm_strike")
        if not atm_strike:
            atm_strike = self.get_atm_strike(chain)

        short_legs_data = []
        short_entry_prices = []

        long_legs_data = []
        long_entry_prices = []

        # Map labels to symbols & prices
        label_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label"): label_map[(ce["label"], "CE")] = ce
            if pe.get("label"): label_map[(pe["label"], "PE")] = pe

        # OTM2 CE (Sell)
        ce_otm2 = label_map.get(("OTM2", "CE"))
        if ce_otm2:
            short_legs_data.append({"symbol": ce_otm2["symbol"], "action": "SELL", "quantity": self.quantity})
            short_entry_prices.append(safe_float(ce_otm2["ltp"]))

        # OTM2 PE (Sell)
        pe_otm2 = label_map.get(("OTM2", "PE"))
        if pe_otm2:
            short_legs_data.append({"symbol": pe_otm2["symbol"], "action": "SELL", "quantity": self.quantity})
            short_entry_prices.append(safe_float(pe_otm2["ltp"]))

        # OTM4 CE (Buy)
        ce_otm4 = label_map.get(("OTM4", "CE"))
        if ce_otm4:
            long_legs_data.append({"symbol": ce_otm4["symbol"], "action": "BUY", "quantity": self.quantity})
            long_entry_prices.append(safe_float(ce_otm4["ltp"]))

        # OTM4 PE (Buy)
        pe_otm4 = label_map.get(("OTM4", "PE"))
        if pe_otm4:
            long_legs_data.append({"symbol": pe_otm4["symbol"], "action": "BUY", "quantity": self.quantity})
            long_entry_prices.append(safe_float(pe_otm4["ltp"]))

        if short_legs_data:
            self.tracker.add_legs(short_legs_data, short_entry_prices, side="SELL")

        if long_legs_data:
            self.long_legs = []
            for i, leg in enumerate(long_legs_data):
                l_data = leg.copy()
                l_data["entry_price"] = safe_float(long_entry_prices[i])
                self.long_legs.append(l_data)

        self.limiter.record()


    def run(self):
        self.logger.info(f"Starting {self.strategy_name} main loop...")
        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.exchange_underlying,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    if self.should_eod_squareoff():
                        self._close_position(chain, "EOD_Squareoff")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.limiter.allow() and self.can_trade_time():
                    atm_strike = chain_resp.get("atm_strike")
                    if not atm_strike:
                        atm_strike = self.get_atm_strike(chain)

                    if atm_strike:
                        straddle_premium = self.calculate_straddle_premium(chain, atm_strike)
                        spot_price = chain_resp.get("underlying_ltp", 0)

                        self.logger.info(format_kv(
                            spot=spot_price,
                            atm=atm_strike,
                            premium=straddle_premium,
                            min_premium=self.min_straddle_premium
                        ))

                        condition = straddle_premium > self.min_straddle_premium

                        # Debouncer to avoid multiple entries on the same signal
                        if self.debouncer.edge("enter_ic", condition):
                            self.logger.info(f"Signal met! Straddle premium {straddle_premium} > {self.min_straddle_premium}")
                            self.execute_entry(chain_resp, chain)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyIronCondor().run()
