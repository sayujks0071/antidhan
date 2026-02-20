#!/usr/bin/env python3
"""
[Nifty Hybrid Trend] - NIFTY Options (OpenAlgo Web UI Compatible)
Hybrid strategy combining SuperTrend (10,3) direction with PCR confirmation to trade Credit Spreads.
"""
import os
import sys
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

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
    import traceback
    traceback.print_exc()
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# ==============================================================================
# CONFIGURATION
# ==============================================================================

API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

# API Key Retrieval Fallback
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


# Strategy Parameters
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyHybridTrend")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = int(os.getenv("QUANTITY", "1"))  # Multiplier (1 lot usually 75/50/25 depending on contract)
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "15"))

# Risk Management
SL_PCT_NET_CREDIT = float(os.getenv("SL_PCT_NET_CREDIT", "50"))   # Stop Loss % of Net Credit
TP_PCT_NET_CREDIT = float(os.getenv("TP_PCT_NET_CREDIT", "80"))   # Take Profit % of Net Credit
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))      # 5 mins between trades
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "3"))

# Indicator Parameters
SUPERTREND_PERIOD = int(os.getenv("SUPERTREND_PERIOD", "10"))
SUPERTREND_MULTIPLIER = float(os.getenv("SUPERTREND_MULTIPLIER", "3.0"))
PCR_BULLISH_THRESHOLD = float(os.getenv("PCR_BULLISH_THRESHOLD", "1.0"))
PCR_BEARISH_THRESHOLD = float(os.getenv("PCR_BEARISH_THRESHOLD", "0.8"))


# ==============================================================================
# UTILITY CLASSES
# ==============================================================================

class NetCreditPositionTracker(OptionPositionTracker):
    """
    Extends OptionPositionTracker to calculate PnL based on Net Credit.
    Ideal for Credit Spreads (Iron Condor, Bull Put, Bear Call).
    """
    def __init__(self, sl_pct_credit, tp_pct_credit, max_hold_min):
        super().__init__(sl_pct=sl_pct_credit, tp_pct=tp_pct_credit, max_hold_min=max_hold_min)
        self.net_credit_collected = 0.0

    def add_legs(self, legs, entry_prices, side):
        """
        Record entry legs and calculate Net Credit.
        side: "SELL" for Credit Spreads (we want credit).
        """
        super().add_legs(legs, entry_prices, side)

        # Calculate Net Credit
        credit = 0.0
        debit = 0.0

        for i, leg in enumerate(self.open_legs):
            price = leg["entry_price"]
            qty = leg.get("quantity", 1)
            action = leg["action"].upper()

            if action == "SELL":
                credit += (price * qty)
            else:
                debit += (price * qty)

        self.net_credit_collected = credit - debit
        # For a credit spread, net_credit_collected should be positive.
        # If negative (Debit Spread), logic might need adjustment, but this class assumes Credit.

    def should_exit(self, chain):
        """
        Calculate PnL as percentage of Net Credit.
        Loss = (Current Net Cost to Close - Net Credit Collected)
        """
        if not self.open_legs:
            return False, [], ""

        # 1. Time Stop
        minutes_held = (datetime.now() - self.entry_time).total_seconds() / 60
        if minutes_held >= self.max_hold_min:
            return True, self.open_legs, "time_stop"

        # 2. Net Credit PnL Check
        # We need to calculate cost to close positions
        # To Close:
        #   Short legs (SELL) -> Must BUY back (Ask Price / LTP)
        #   Long legs (BUY) -> Must SELL back (Bid Price / LTP)

        cost_to_close = 0.0

        ltp_map = {}
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("symbol"): ltp_map[ce["symbol"]] = safe_float(ce.get("ltp"))
            if pe.get("symbol"): ltp_map[pe["symbol"]] = safe_float(pe.get("ltp"))

        for leg in self.open_legs:
            sym = leg["symbol"]
            qty = leg.get("quantity", 1)
            action = leg["action"].upper()
            # If no LTP, use entry price (neutral assumption)
            curr_price = ltp_map.get(sym, leg["entry_price"])

            if action == "SELL":
                # Closing a Short -> Buy it back -> Debit
                cost_to_close += (curr_price * qty)
            else:
                # Closing a Long -> Sell it back -> Credit (reduces cost)
                cost_to_close -= (curr_price * qty)

        # PnL = Net Credit Collected - Cost to Close
        pnl = self.net_credit_collected - cost_to_close

        # PnL % = (PnL / Net Credit) * 100
        if self.net_credit_collected == 0:
             # Avoid division by zero
            return False, [], ""

        pnl_pct = (pnl / self.net_credit_collected) * 100

        # Stop Loss: if pnl_pct < -SL_PCT (e.g., -50%)
        # Example: Collected 100. Cost to Close 150. PnL = -50. -50/100 = -50%.
        if pnl_pct <= -self.sl_pct:
            return True, self.open_legs, f"stop_loss_hit ({pnl_pct:.1f}%)"

        # Take Profit: if pnl_pct > TP_PCT (e.g., 80%)
        # Example: Collected 100. Cost to Close 20. PnL = 80. 80/100 = 80%.
        if pnl_pct >= self.tp_pct:
            return True, self.open_legs, f"take_profit_hit ({pnl_pct:.1f}%)"

        return False, [], ""


def calculate_supertrend(df, period=10, multiplier=3):
    """
    Calculate SuperTrend indicator.
    Returns: pd.DataFrame with 'supertrend' and 'direction' columns.
    """
    if df.empty:
        return pd.DataFrame()

    high = df['high']
    low = df['low']
    close = df['close']

    # Calculate ATR
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    # Basic Upper/Lower Bands
    hl2 = (high + low) / 2
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    # Final Bands
    final_upper = [0.0] * len(df)
    final_lower = [0.0] * len(df)

    # Direction: 1 (Up), -1 (Down)
    direction = [1] * len(df)
    supertrend = [0.0] * len(df)

    # Initialize
    close_val = close.values
    bu = basic_upper.values
    bl = basic_lower.values

    # Iterative calculation
    for i in range(1, len(df)):
        # Upper Band
        if bu[i] < final_upper[i-1] or close_val[i-1] > final_upper[i-1]:
            final_upper[i] = bu[i]
        else:
            final_upper[i] = final_upper[i-1]

        # Lower Band
        if bl[i] > final_lower[i-1] or close_val[i-1] < final_lower[i-1]:
            final_lower[i] = bl[i]
        else:
            final_lower[i] = final_lower[i-1]

        # Trend Direction
        if direction[i-1] == 1: # Trend was Up
            if close_val[i] < final_lower[i]:
                direction[i] = -1
                supertrend[i] = final_upper[i]
            else:
                direction[i] = 1
                supertrend[i] = final_lower[i]
        else: # Trend was Down
            if close_val[i] > final_upper[i]:
                direction[i] = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i] = -1
                supertrend[i] = final_upper[i]

    df = df.copy()
    df['supertrend'] = supertrend
    df['direction'] = direction
    return df


# ==============================================================================
# STRATEGY CLASS
# ==============================================================================

class NiftyHybridTrendStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.api_key = API_KEY
        self.host = HOST

        # Clients
        self.client = OptionChainClient(api_key=self.api_key, host=self.host)
        self.api_client = APIClient(api_key=self.api_key, host=self.host)

        # Utilities
        self.tracker = NetCreditPositionTracker(
            sl_pct_credit=SL_PCT_NET_CREDIT,
            tp_pct_credit=TP_PCT_NET_CREDIT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=3,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.ledger = TradeLedger(os.path.join(strategies_dir, "logs", f"{STRATEGY_NAME}_trades.csv"))

        # State
        self.expiry = None
        self.last_expiry_check = 0
        self.entered_today = False

    def ensure_expiry(self):
        """Refreshes expiry date if needed."""
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > EXPIRY_REFRESH_SEC):
            self.logger.info("Refreshing expiry dates...")
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                self.expiry = choose_nearest_expiry(dates)
                self.logger.info(f"Selected Expiry: {self.expiry}")
                self.last_expiry_check = now
            else:
                self.logger.error(f"Failed to fetch expiry: {res.get('message')}")

    def get_market_data(self):
        """Fetches Option Chain and Historical Data."""
        # Option Chain
        chain_resp = self.client.optionchain(
            underlying=UNDERLYING,
            exchange=UNDERLYING_EXCHANGE,
            expiry_date=self.expiry,
            strike_count=STRIKE_COUNT
        )

        # Historical Data (5m candles)
        # End date is today, Start date is 5 days ago to ensure enough data for SuperTrend
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

        history_df = self.api_client.history(
            symbol=UNDERLYING,
            exchange=UNDERLYING_EXCHANGE,
            interval="5m",
            start_date=start_date,
            end_date=end_date
        )

        return chain_resp, history_df

    def calculate_indicators(self, chain, history_df):
        """Calculates SuperTrend and PCR."""
        indicators = {}

        # 1. SuperTrend
        if not history_df.empty and len(history_df) > 20:
            st_df = calculate_supertrend(history_df, period=SUPERTREND_PERIOD, multiplier=SUPERTREND_MULTIPLIER)
            last_row = st_df.iloc[-1]
            indicators['trend_direction'] = int(last_row['direction']) # 1 or -1
            indicators['supertrend_val'] = float(last_row['supertrend'])
            indicators['close'] = float(last_row['close'])
        else:
            indicators['trend_direction'] = 0

        # 2. PCR (Put Call Ratio)
        total_ce_oi = 0
        total_pe_oi = 0

        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            total_ce_oi += safe_int(ce.get("oi", 0))
            total_pe_oi += safe_int(pe.get("oi", 0))

        if total_ce_oi > 0:
            indicators['pcr'] = total_pe_oi / total_ce_oi
        else:
            indicators['pcr'] = 0.0

        return indicators

    def execute_strategy(self, chain, indicators):
        """Main Strategy Logic."""

        trend = indicators.get('trend_direction', 0)
        pcr = indicators.get('pcr', 0.0)
        spot = indicators.get('close', 0.0)

        self.logger.info(format_kv(
            spot=f"{spot:.2f}",
            trend=trend,
            pcr=f"{pcr:.2f}",
            active_legs=len(self.tracker.open_legs)
        ))

        # Define Entry Signals
        # Bullish: Up Trend + High PCR (Put Support)
        bullish_signal = (trend == 1) and (pcr >= PCR_BULLISH_THRESHOLD)

        # Bearish: Down Trend + Low PCR (Call Resistance)
        bearish_signal = (trend == -1) and (pcr <= PCR_BEARISH_THRESHOLD)

        # Debounce Signals
        bullish_edge = self.debouncer.edge("bullish_entry", bullish_signal)
        bearish_edge = self.debouncer.edge("bearish_entry", bearish_signal)

        if not self.limiter.allow():
            return

        if bullish_edge:
            self.logger.info("Signal: BULLISH (Trend UP + High PCR). Placing Bull Put Spread.")
            self._place_credit_spread(chain, "PE", "OTM2", "OTM5") # Sell OTM2 PE, Buy OTM5 PE

        elif bearish_edge:
            self.logger.info("Signal: BEARISH (Trend DOWN + Low PCR). Placing Bear Call Spread.")
            self._place_credit_spread(chain, "CE", "OTM2", "OTM5") # Sell OTM2 CE, Buy OTM5 CE

    def _place_credit_spread(self, chain, option_type, sell_offset, buy_offset):
        """
        Places a Credit Spread Order.
        Bull Put Spread: Sell PE (Closer), Buy PE (Farther)
        Bear Call Spread: Sell CE (Closer), Buy CE (Farther)
        """
        try:
            # Construct Legs
            legs = [
                {"offset": sell_offset, "option_type": option_type, "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                {"offset": buy_offset, "option_type": option_type, "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
            ]

            self.logger.info(f"Placing Order: {legs}")

            response = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=UNDERLYING_EXCHANGE,
                expiry_date=self.expiry,
                legs=legs
            )

            if response.get("status") == "success":
                # We need entry prices to track PnL. The response might not contain filled prices immediately.
                # In a real scenario, we'd query orderbook. Here we approximate using current Chain LTPs.
                entry_prices = []
                filled_legs = []

                # Fetch symbols from response or re-calculate from chain
                # The response 'data' usually contains order IDs.
                # We will resolve symbols from Chain for tracking purposes.

                # Re-find the symbols based on offsets
                # Note: This is an approximation. In production, listen to order updates.
                # But for this standalone script, we track based on what we INTENDED to trade.

                atm_strike = 0
                for item in chain:
                    if item.get("ce", {}).get("label") == "ATM":
                        atm_strike = item["strike"]
                        break

                # Locate strikes for offsets
                # This logic replicates backend offset logic briefly to find LTPs
                # Assuming chain is sorted by strike
                # ... skipping complex offset resolution here for brevity,
                # instead we will trust the Tracker to update if we had exact symbols.

                # Since we don't have exact symbols from response (only order IDs usually),
                # we will rely on the fact that OpenAlgo executes them.
                # To track them properly, we need to know WHICH symbols were traded.
                # Let's assume the user/platform handles execution.

                # However, OptionPositionTracker needs symbols to track PnL.
                # We MUST resolve symbols.

                # Let's use the 'legs' from request and resolve symbols from chain manually
                # to populate the tracker.

                resolved_legs = self._resolve_legs_from_chain(chain, legs)
                if resolved_legs:
                    entry_prices = [leg['ltp'] for leg in resolved_legs]
                    # Update tracker
                    self.tracker.add_legs(resolved_legs, entry_prices, side="SELL") # Credit Spread is a SELL strategy

                    self.limiter.record()
                    self.ledger.append({
                        "timestamp": datetime.now().isoformat(),
                        "signal": "CREDIT_SPREAD",
                        "details": str(legs)
                    })
                    self.logger.info("Order placed and tracked.")
                else:
                    self.logger.warning("Order placed but could not resolve legs for tracking.")

            else:
                self.logger.error(f"Order Failed: {response.get('message')}")

        except Exception as e:
            self.logger.error(f"Execution Error: {e}")

    def _resolve_legs_from_chain(self, chain, legs_config):
        """
        Helper to find symbols and LTPs for the requested offsets.
        Returns list of dicts with {symbol, action, ltp, quantity}
        """
        # Find ATM index
        atm_idx = -1
        for i, item in enumerate(chain):
            if item.get("ce", {}).get("label") == "ATM":
                atm_idx = i
                break

        if atm_idx == -1: return []

        resolved = []
        for leg in legs_config:
            offset = leg["offset"] # e.g., "OTM2", "ATM"
            otype = leg["option_type"].lower() # "ce" or "pe"

            target_idx = atm_idx

            # Parse Offset (Simple parser)
            if offset == "ATM":
                pass
            elif "OTM" in offset:
                n = int(offset.replace("OTM", ""))
                # For CE, OTM is Higher Strike (Index + n)
                # For PE, OTM is Lower Strike (Index - n)
                if otype == "ce":
                    target_idx = atm_idx + n
                else:
                    target_idx = atm_idx - n
            elif "ITM" in offset:
                n = int(offset.replace("ITM", ""))
                # For CE, ITM is Lower Strike (Index - n)
                # For PE, ITM is Higher Strike (Index + n)
                if otype == "ce":
                    target_idx = atm_idx - n
                else:
                    target_idx = atm_idx + n

            # Check bounds
            if 0 <= target_idx < len(chain):
                item = chain[target_idx]
                opt_data = item.get(otype, {})
                resolved.append({
                    "symbol": opt_data.get("symbol"),
                    "action": leg["action"],
                    "quantity": leg["quantity"],
                    "ltp": safe_float(opt_data.get("ltp"))
                })
            else:
                return [] # Out of bounds

        return resolved

    def _close_position(self, chain, reason):
        """Closes all open positions."""
        self.logger.info(f"Exiting Position. Reason: {reason}")

        # We need to reverse the actions
        # Tracker has open_legs.
        exit_legs = []
        for leg in self.tracker.open_legs:
            # Reverse Action
            exit_action = "SELL" if leg["action"].upper() == "BUY" else "BUY"
            exit_legs.append({
                "symbol": leg["symbol"], # API supports symbol in optionsmultiorder?
                # optionsmultiorder expects 'offset' usually, or we use placesmartorder loop.
                # But optionsmultiorder is for STRATEGY based offsets.

                # If we want to exit specific symbols, we should use 'placesmartorder' loop
                # OR 'optionsmultiorder' if the API supports explicit symbols in legs (it might not).

                # Given API constraints, let's loop placesmartorder for safety.
                # Or checks if optionsmultiorder supports 'symbol' instead of 'offset'.
                # The doc says: legs=[{"offset": "OTM2" ...}]

                # Let's use placesmartorder loop for exiting specific symbols.
            })

            self.client.placesmartorder(
                strategy=STRATEGY_NAME,
                symbol=leg["symbol"],
                action=exit_action,
                exchange=OPTIONS_EXCHANGE,
                pricetype="MARKET",
                product=PRODUCT,
                quantity=leg["quantity"],
                position_size=0
            )
            time.sleep(0.2) # Avoid rate limits

        self.tracker.clear()
        self.logger.info("Position Closed.")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} Strategy...")
        self.logger.info(f"Configs: SL_NET={SL_PCT_NET_CREDIT}% TP_NET={TP_PCT_NET_CREDIT}% Time={MAX_HOLD_MIN}m")

        while True:
            try:
                # 1. Market Hours Check
                if not is_market_open():
                    self.logger.info("Market is closed. Sleeping...")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 2. Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    self.logger.warning("No expiry found. Sleeping...")
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch Data
                chain_resp, history_df = self.get_market_data()

                valid, reason = is_chain_valid(chain_resp, min_strikes=5)
                if not valid:
                    self.logger.warning(f"Invalid Chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])

                # 4. Exit Management (Priority)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        # Reset entered_today logic if needed, or enforce 1 trade/day?
                        # If MAX_ORDERS is high, we continue.
                        time.sleep(SLEEP_SECONDS)
                        continue

                    # EOD Exit (15:15)
                    now_time = datetime.now().time()
                    if now_time >= datetime.strptime("15:15", "%H:%M").time():
                        self._close_position(chain, "EOD_Squareoff")
                        time.sleep(SLEEP_SECONDS)
                        continue

                # 5. Entry Logic
                if not self.tracker.open_legs:
                    indicators = self.calculate_indicators(chain, history_df)
                    self.execute_strategy(chain, indicators)

            except KeyboardInterrupt:
                self.logger.info("Strategy stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Error in Main Loop: {e}")
                import traceback
                traceback.print_exc()

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftyHybridTrendStrategy()
    strategy.run()
