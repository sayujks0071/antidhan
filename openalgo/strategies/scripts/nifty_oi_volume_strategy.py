#!/usr/bin/env python3
"""
Nifty_OI_Volume_Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Identifies OI walls and enters on volume surges near them.
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
        safe_float,
        safe_int,
    )
    from strategy_common import SignalDebouncer, TradeLimiter, format_kv
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

# Configuration via os.getenv
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "Nifty_OI_Volume_Surge")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")

PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "20"))

SL_PCT = float(os.getenv("SL_PCT", "30.0"))
TP_PCT = float(os.getenv("TP_PCT", "60.0"))
MAX_HOLD_MIN = float(os.getenv("MAX_HOLD_MIN", "20.0"))

COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "60"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "15"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "10"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "3"))

WALL_PROXIMITY_PCT = float(os.getenv("WALL_PROXIMITY_PCT", "0.002")) # 0.2% proximity to wall
VOLUME_SURGE_MULTIPLIER = float(os.getenv("VOLUME_SURGE_MULTIPLIER", "1.5"))


class StrategyClass:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.limiter = TradeLimiter(max_per_day=MAX_ORDERS_PER_DAY, max_per_hour=MAX_ORDERS_PER_HOUR, cooldown_seconds=COOLDOWN_SECONDS)
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_refresh = 0

        self.call_wall_strike = None
        self.put_wall_strike = None

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > EXPIRY_REFRESH_SEC:
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res.get("status") == "success" and res.get("data"):
                self.expiry = choose_nearest_expiry(res["data"])
                self.last_expiry_refresh = now
                self.logger.info(f"Resolved expiry: {self.expiry}")
            else:
                self.logger.warning(f"Failed to fetch expiry: {res}")

    def update_oi_walls(self, chain):
        max_call_oi = -1
        max_put_oi = -1
        call_wall = None
        put_wall = None

        for item in chain:
            strike = item["strike"]
            ce_oi = safe_int(item.get("ce", {}).get("oi", 0))
            pe_oi = safe_int(item.get("pe", {}).get("oi", 0))

            if ce_oi > max_call_oi:
                max_call_oi = ce_oi
                call_wall = strike

            if pe_oi > max_put_oi:
                max_put_oi = pe_oi
                put_wall = strike

        self.call_wall_strike = call_wall
        self.put_wall_strike = put_wall

    def check_volume_surge(self):
        try:
            df = self.api_client.history(
                symbol=UNDERLYING,
                exchange=UNDERLYING_EXCHANGE,
                interval="5m",
                start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                end_date=datetime.now().strftime("%Y-%m-%d")
            )
            if df is None or df.empty or len(df) < 20:
                return False

            avg_vol = df['volume'].rolling(20).mean().iloc[-2]  # previous 20 bars
            current_vol = df['volume'].iloc[-1]

            if current_vol > avg_vol * VOLUME_SURGE_MULTIPLIER:
                return True
        except Exception as e:
            self.logger.error(f"Error checking volume surge: {e}")

        return False

    def _close_position(self, chain, reason):
        if not self.tracker.open_legs:
            return

        self.logger.info(format_kv(event="trade", action="CLOSE", reason=reason))

        for leg in self.tracker.open_legs:
            close_action = "SELL" if leg["action"] == "BUY" else "BUY"

            resp = self.api_client.placesmartorder(
                strategy=STRATEGY_NAME,
                symbol=leg["symbol"],
                action=close_action,
                exchange=OPTIONS_EXCHANGE,
                pricetype="MARKET",
                product=PRODUCT,
                quantity=leg["quantity"],
                position_size=0
            )
            self.logger.info(f"Trade response: {resp}")

        self.tracker.clear()

    def _enter_position(self, chain, option_type):
        atm_strike = None
        atm_symbol = None
        atm_ltp = 0.0

        for item in chain:
            opt_data = item.get(option_type.lower(), {})
            if opt_data.get("label") == "ATM":
                atm_strike = item["strike"]
                atm_symbol = opt_data.get("symbol")
                atm_ltp = safe_float(opt_data.get("ltp"))
                break

        if not atm_symbol:
            self.logger.warning(f"Could not find ATM {option_type}")
            return

        self.logger.info(format_kv(event="trade", action="OPEN", type=option_type, symbol=atm_symbol, ltp=atm_ltp))

        resp = self.api_client.placesmartorder(
            strategy=STRATEGY_NAME,
            symbol=atm_symbol,
            action="BUY",
            exchange=OPTIONS_EXCHANGE,
            pricetype="MARKET",
            product=PRODUCT,
            quantity=QUANTITY,
            position_size=QUANTITY
        )
        self.logger.info(f"Trade response: {resp}")

        legs = [{
            "symbol": atm_symbol,
            "action": "BUY",
            "quantity": QUANTITY
        }]

        self.tracker.add_legs(legs, [atm_ltp], side="BUY")
        self.tracker.trade_type = option_type

    def can_trade(self):
        if not self.limiter.allow():
            return False

        now_time = datetime.now().time()

        if now_time < datetime.strptime("09:30:00", "%H:%M:%S").time():
            return False

        if now_time > datetime.strptime("14:30:00", "%H:%M:%S").time():
            return False

        return True

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME}...")

        while True:
            try:
                if not is_market_open():
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10)
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                spot_price = safe_float(chain_resp.get("underlying_ltp"))

                if spot_price <= 0:
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.update_oi_walls(chain)

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # Dynamic SL based on wall breach
                    if hasattr(self.tracker, 'trade_type'):
                        if self.tracker.trade_type == "CE" and self.put_wall_strike and spot_price < self.put_wall_strike:
                            exit_now = True
                            exit_reason = "support_wall_breach"
                        elif self.tracker.trade_type == "PE" and self.call_wall_strike and spot_price > self.call_wall_strike:
                            exit_now = True
                            exit_reason = "resistance_wall_breach"

                    # EOD Square-off
                    now_time = datetime.now().time()
                    if now_time >= datetime.strptime("15:15:00", "%H:%M:%S").time():
                        exit_now = True
                        exit_reason = "eod_square_off"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade() and self.call_wall_strike and self.put_wall_strike:
                    dist_to_call_wall = abs(spot_price - self.call_wall_strike) / spot_price
                    dist_to_put_wall = abs(spot_price - self.put_wall_strike) / spot_price

                    is_near_call_wall = dist_to_call_wall <= WALL_PROXIMITY_PCT
                    is_near_put_wall = dist_to_put_wall <= WALL_PROXIMITY_PCT

                    if is_near_call_wall or is_near_put_wall:
                        vol_surge = self.check_volume_surge()

                        can_buy_ce = is_near_put_wall and vol_surge
                        can_buy_pe = is_near_call_wall and vol_surge

                        buy_ce_signal = self.debouncer.edge("buy_ce", can_buy_ce)
                        buy_pe_signal = self.debouncer.edge("buy_pe", can_buy_pe)

                        if buy_ce_signal or buy_pe_signal:
                            self.logger.info(format_kv(
                                spot=spot_price,
                                call_wall=self.call_wall_strike,
                                put_wall=self.put_wall_strike,
                                vol_surge=vol_surge,
                                buy_ce=buy_ce_signal,
                                buy_pe=buy_pe_signal
                            ))

                        if buy_ce_signal:
                            self._enter_position(chain, option_type="CE")
                            self.limiter.record()
                        elif buy_pe_signal:
                            self._enter_position(chain, option_type="PE")
                            self.limiter.record()

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    StrategyClass().run()
