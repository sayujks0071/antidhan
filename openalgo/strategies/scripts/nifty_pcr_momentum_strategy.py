#!/usr/bin/env python3
"""
Nifty PCR Momentum - NIFTY Options (OpenAlgo Web UI Compatible)
Buys ATM CE when PCR > 1.3, buys ATM PE when PCR < 0.7, tracks positions with Stop Loss and Take Profit.
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


class NiftyPCRStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "NIFTY_PCR_MOMENTUM")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Management
        self.sl_pct = float(os.getenv("SL_PCT", "50")) # 50% stop loss
        self.tp_pct = float(os.getenv("TP_PCT", "80")) # 80% take profit
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Entry Filters
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "20"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "20"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "15"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "3"))

        self.pcr_bull_threshold = float(os.getenv("PCR_BULL_THRESHOLD", "1.3"))
        self.pcr_bear_threshold = float(os.getenv("PCR_BEAR_THRESHOLD", "0.7"))

        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_refresh = 0

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res.get("status") == "success" and res.get("data"):
                    dates = res["data"]
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                else:
                    self.logger.error("Failed to fetch expiries")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def calculate_pcr(self, chain):
        total_ce_oi = 0
        total_pe_oi = 0

        for item in chain:
            ce_oi = safe_int(item.get("ce", {}).get("oi", 0))
            pe_oi = safe_int(item.get("pe", {}).get("oi", 0))
            total_ce_oi += ce_oi
            total_pe_oi += pe_oi

        if total_ce_oi == 0:
            return 0.0

        return total_pe_oi / total_ce_oi

    def _close_position(self, chain, reason):
        self.logger.info(f"event=exit reason={reason}")

        for leg in self.tracker.open_legs:
            try:
                # To close a BUY position, we SELL it.
                close_action = "SELL" if leg["action"] == "BUY" else "BUY"

                # We need to find the specific symbol to close it
                symbol = leg.get("symbol")
                if not symbol:
                    # if no symbol stored, try to recreate offset via place smart order
                    continue

                resp = self.client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg["quantity"],
                    position_size=0
                )
                self.logger.info(f"Trade response: Closed leg {symbol} with response {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg}: {e}")

        self.tracker.clear()

    def _open_position(self, signal, chain_resp, atm_strike):
        chain = chain_resp.get("chain", [])

        option_type = "CE" if signal == "BUY_CE" else "PE"

        legs = [
            {"offset": "ATM", "option_type": option_type, "action": "BUY", "quantity": self.quantity, "product": self.product}
        ]

        try:
            response = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.underlying_exchange,
                expiry_date=self.expiry,
                legs=legs
            )
            self.logger.info(f"Trade response: Opened position with response {response}")

            # Record in tracker
            # Find the ATM option in the chain to record entry price
            entry_prices = []
            recorded_legs = []

            for item in chain:
                if item.get("strike") == atm_strike:
                    opt_data = item.get(option_type.lower(), {})
                    ltp = safe_float(opt_data.get("ltp", 0.0))
                    symbol = opt_data.get("symbol", "")

                    if ltp > 0:
                        entry_prices.append(ltp)
                        recorded_legs.append({
                            "symbol": symbol,
                            "action": "BUY",
                            "quantity": self.quantity,
                            "option_type": option_type
                        })
                    break

            if entry_prices:
                self.tracker.add_legs(recorded_legs, entry_prices, side="BUY")
                self.logger.info(f"event=trade position=opened side=BUY option={option_type} price={entry_prices[0]}")
            else:
                self.logger.warning("Could not record entry price in tracker, position tracking may be incorrect")

            self.limiter.record()

        except Exception as e:
            self.logger.error(f"Error placing order: {e}")

    def can_trade(self):
        current_time = datetime.now().time()
        # Don't trade before 9:30 AM or after 2:30 PM
        if current_time.hour < 9 or (current_time.hour == 9 and current_time.minute < 30):
            return False
        if current_time.hour > 14 or (current_time.hour == 14 and current_time.minute > 30):
            return False

        return self.limiter.allow()

    def check_eod_exit(self, chain):
        current_time = datetime.now().time()
        # Exit before 3:15 PM
        if current_time.hour == 15 and current_time.minute >= 10:
            if self.tracker.open_legs:
                self._close_position(chain, "eod_square_off")
                return True
        return False

    def run(self):
        self.logger.info(f"Starting Nifty PCR Momentum Strategy. Monitoring {self.underlying} PCR.")

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
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=5, require_oi=True)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")
                underlying_ltp = chain_resp.get("underlying_ltp")

                # EOD Exit
                if self.check_eod_exit(chain):
                    time.sleep(self.sleep_seconds)
                    continue

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS
                pcr = self.calculate_pcr(chain)

                bull_signal = self.debouncer.edge("pcr_bull", pcr > self.pcr_bull_threshold)
                bear_signal = self.debouncer.edge("pcr_bear", pcr < self.pcr_bear_threshold)

                self.logger.info(format_kv(spot=underlying_ltp, pcr=round(pcr, 3), atm=atm_strike, signal="NONE" if not (bull_signal or bear_signal) else "BUY_CE" if bull_signal else "BUY_PE"))

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    if bull_signal:
                        self.logger.info(f"Bullish signal triggered. PCR {pcr:.3f} > {self.pcr_bull_threshold}")
                        self._open_position("BUY_CE", chain_resp, atm_strike)
                    elif bear_signal:
                        self.logger.info(f"Bearish signal triggered. PCR {pcr:.3f} < {self.pcr_bear_threshold}")
                        self._open_position("BUY_PE", chain_resp, atm_strike)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    strategy = NiftyPCRStrategy()
    strategy.run()
