#!/usr/bin/env python3
"""
Nifty Smart Options - NIFTY Options (OpenAlgo Web UI Compatible)
Hybrid strategy that uses EMA(20) and PCR to detect market regimes (Bullish/Bearish/Neutral)
and trades Bull Put Spreads, Bear Call Spreads, or Iron Condors accordingly.
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
    from trading_utils import is_market_open, APIClient
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


class NiftySmartOptions:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftySmartOptions")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Parameters (Ensure 2:1 R:R equivalent using percentages)
        self.sl_pct = float(os.getenv("SL_PCT", "30.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "60.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Time Management
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "60"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # Trade Limits
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "3"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

        # EMA timeframe
        self.ema_period = 20

        # State
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.option_client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()
        ledger_path = os.path.join(script_dir, "trades_smart_options.csv")
        self.ledger = TradeLedger(ledger_path)

        self.expiry = None
        self.last_expiry_refresh = 0
        self.current_position_legs = []

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            manual_expiry = os.getenv("EXPIRY_DATE")
            if manual_expiry:
                self.expiry = normalize_expiry(manual_expiry)
                self.last_expiry_refresh = now
                self.logger.info(f"Using manual expiry: {self.expiry}")
                return

            try:
                res = self.option_client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                else:
                    self.logger.warning("Failed to fetch expiry dates.")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade_now(self):
        if not is_market_open():
            return False

        now = datetime.now().time()
        # Ensure after 9:30 AM (skip first 15 mins) and before 3:00 PM
        start_time = datetime.strptime("09:30", "%H:%M").time()
        end_time = datetime.strptime("15:00", "%H:%M").time()

        if now < start_time or now > end_time:
            return False

        return True

    def _close_position(self, exit_reason):
        """Closes all legs individually using placesmartorder and reverses the action."""
        if not self.current_position_legs:
            return

        self.logger.info(f"event=exit reason={exit_reason}")

        for leg in self.current_position_legs:
            symbol = leg.get("symbol")
            action = leg.get("action")
            qty = leg.get("quantity", self.quantity)

            # Reverse action
            exit_action = "BUY" if action.upper() == "SELL" else "SELL"

            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=exit_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=qty,
                    position_size=qty
                )
                self.logger.info(f"Closed {symbol} {exit_action}: {resp}")
            except Exception as e:
                self.logger.error(f"Failed to close {symbol}: {e}")

        self.ledger.append({
            "timestamp": datetime.now().isoformat(),
            "side": "EXIT",
            "reason": exit_reason,
            "details": f"Closed legs: {[leg.get('symbol') for leg in self.current_position_legs]}"
        })
        self.tracker.clear()
        self.current_position_legs = []

    def get_market_regime(self):
        """Calculates EMA and PCR to determine regime."""
        # Fetch underlying history
        df = self.api_client.history(
            symbol=self.underlying,
            exchange=self.underlying_exchange,
            interval="5m",
            start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
            end_date=datetime.now().strftime("%Y-%m-%d")
        )

        underlying_ltp = 0.0
        ema_val = 0.0

        if not df.empty and len(df) >= self.ema_period:
            df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()
            ema_val = float(df['ema'].iloc[-1])
            underlying_ltp = float(df['close'].iloc[-1])

        return underlying_ltp, ema_val

    def calculate_pcr(self, chain):
        """Calculates Put-Call Ratio based on OI."""
        total_put_oi = sum(safe_int(item.get("pe", {}).get("oi", 0)) for item in chain)
        total_call_oi = sum(safe_int(item.get("ce", {}).get("oi", 0)) for item in chain)

        if total_call_oi == 0:
            return 1.0
        return total_put_oi / total_call_oi

    def execute_strategy(self, regime, chain):
        """Executes Bull Put Spread, Bear Call Spread, or Iron Condor."""
        legs = []

        if regime == "BULLISH":
            # Bull Put Spread: Sell OTM1 PE, Buy OTM3 PE
            legs = [
                {"offset": "OTM3", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                {"offset": "OTM1", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product}
            ]
        elif regime == "BEARISH":
            # Bear Call Spread: Sell OTM1 CE, Buy OTM3 CE
            legs = [
                {"offset": "OTM3", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                {"offset": "OTM1", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product}
            ]
        elif regime == "NEUTRAL":
            # Iron Condor: Sell OTM2 CE/PE, Buy OTM4 CE/PE
            legs = [
                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product}
            ]

        if not legs:
            return

        try:
            resp = self.option_client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.underlying_exchange,
                expiry_date=self.expiry,
                legs=legs
            )
            self.logger.info(f"event=trade regime={regime} response={resp}")

            # We need to extract the option symbols and prices from the chain
            # to populate tracker.
            # To do this correctly, we simulate what optionsmultiorder does internally
            # or extract it from the response if it returns the executed legs.
            # Assuming we can't get it from response reliably, we map offsets from chain.

            # Find ATM
            atm_strike = None
            for item in chain:
                if item.get("ce", {}).get("label") == "ATM":
                    atm_strike = item.get("strike")
                    break

            if atm_strike:
                # We need to track all executed legs for closing later
                all_legs = []
                sell_legs_to_track = []
                sell_prices = []

                for req_leg in legs:
                    offset = req_leg["offset"]
                    otype = req_leg["option_type"].lower()

                    for item in chain:
                        opt_data = item.get(otype, {})
                        if opt_data.get("label") == offset:
                            leg_info = {
                                "symbol": opt_data.get("symbol"),
                                "action": req_leg["action"].upper(),
                                "quantity": req_leg["quantity"]
                            }
                            all_legs.append(leg_info)

                            if req_leg["action"].upper() == "SELL":
                                sell_legs_to_track.append(leg_info)
                                sell_prices.append(safe_float(opt_data.get("ltp")))
                            break

                self.current_position_legs = all_legs

                if sell_legs_to_track:
                    self.tracker.add_legs(sell_legs_to_track, sell_prices, side="SELL")
                    self.limiter.record()
                    self.ledger.append({
                        "timestamp": datetime.now().isoformat(),
                        "side": "ENTRY",
                        "reason": f"Regime: {regime}",
                        "details": f"Tracked legs: {sell_legs_to_track}"
                    })

        except Exception as e:
            self.logger.error(f"Error executing trade: {e}")


    def run(self):
        self.logger.info(f"Starting {self.strategy_name} Strategy...")

        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # EOD Square-off check (3:15 PM)
                now_time = datetime.now().time()
                square_off_time = datetime.strptime("15:15", "%H:%M").time()

                if now_time >= square_off_time and self.tracker.open_legs:
                    self._close_position("eod_square_off")
                    time.sleep(self.sleep_seconds)
                    continue

                # Fetch Chain
                chain_resp = self.option_client.optionchain(
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

                # 1. EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # 2. CALCULATE INDICATORS & ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade_now() and self.limiter.allow():
                    underlying_ltp, ema_val = self.get_market_regime()
                    pcr = self.calculate_pcr(chain)

                    if underlying_ltp > 0 and ema_val > 0:
                        regime = "NEUTRAL"
                        if underlying_ltp > ema_val and pcr > 1.2:
                            regime = "BULLISH"
                        elif underlying_ltp < ema_val and pcr < 0.8:
                            regime = "BEARISH"

                        self.logger.info(format_kv(spot=underlying_ltp, ema=ema_val, pcr=round(pcr, 2), regime=regime))

                        # Debounce regime signal to prevent rapid firing
                        if self.debouncer.edge(f"signal_{regime}", True):
                            self.execute_strategy(regime, chain)

            except Exception as e:
                self.logger.error(f"Main loop error: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    strategy = NiftySmartOptions()
    strategy.run()
