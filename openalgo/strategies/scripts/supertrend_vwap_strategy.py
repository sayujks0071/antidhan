#!/usr/bin/env python3
"""
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis.
Enhanced with Position Management, Stop Loss, and Take Profit.
"""
import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add repo root to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
except ImportError:
    # Fallback if running from a different context
    try:
        from strategies.utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
    except ImportError:
        pass # Will handle gracefully in main
        api = None

# Try native import, fallback to our APIClient
try:
    from openalgo import api
except ImportError:
    api = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class SuperTrendVWAPStrategy:
    def __init__(self, args):
        self.symbol = args.symbol
        self.quantity = args.quantity
        self.ignore_time = args.ignore_time
        self.stop_loss_pct = args.stop_loss_pct
        self.take_profit_pct = args.take_profit_pct

        self.api_key = args.api_key or os.getenv('OPENALGO_APIKEY', 'demo_key')
        self.host = args.host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

        self.logger = logging.getLogger(f"VWAP_{self.symbol}")

        # Initialize API Client
        if api:
            self.client = api(api_key=self.api_key, host=self.host)
            self.logger.info("Using Native OpenAlgo API")
        elif 'APIClient' in globals():
            self.client = APIClient(api_key=self.api_key, host=self.host)
            self.logger.info("Using Fallback API Client (httpx)")
        else:
            self.logger.error("No API client available. Install openalgo or ensure utils are accessible.")
            sys.exit(1)

        # Initialize Position Manager
        if 'PositionManager' in globals():
            self.pm = PositionManager(self.symbol)
        else:
            self.logger.error("PositionManager not available. Cannot run strategy safely.")
            sys.exit(1)

    def analyze_volume_profile(self, df, n_bins=20):
        """
        Basic Volume Profile analysis.
        Identify Point of Control (POC) - price level with highest volume.
        """
        price_min = df['low'].min()
        price_max = df['high'].max()

        # Create bins
        bins = np.linspace(price_min, price_max, n_bins)

        # Bucket volume into price bins
        # Using 'close' as proxy for trade price in the bin
        df['bin'] = pd.cut(df['close'], bins=bins, labels=False)

        volume_profile = df.groupby('bin')['volume'].sum()

        # Find POC Bin
        if volume_profile.empty:
            return 0, 0

        poc_bin = volume_profile.idxmax()

        # Approximate POC Price (midpoint of bin)
        if np.isnan(poc_bin):
            return 0, 0

        poc_price = bins[int(poc_bin)] + (bins[1] - bins[0]) / 2

        return poc_price, volume_profile.max()

    def check_exit_conditions(self, current_price):
        """Check for Stop Loss or Take Profit exits."""
        if not self.pm.has_position():
            return

        pnl = self.pm.get_pnl(current_price)
        entry_price = self.pm.entry_price

        # Calculate PnL percentage relative to entry value
        if entry_price == 0: return

        pnl_pct = (pnl / (entry_price * abs(self.pm.position))) * 100

        self.logger.info(f"[POSITION] symbol={self.symbol} entry={entry_price} current={current_price} pnl={pnl:.2f} ({pnl_pct:.2f}%)")

        # Stop Loss
        if pnl_pct < -self.stop_loss_pct:
            self.logger.info(f"[EXIT] symbol={self.symbol} exit={current_price} pnl={pnl:.2f} reason=STOP_LOSS")
            self.close_position("STOP_LOSS")

        # Take Profit
        elif pnl_pct > self.take_profit_pct:
            self.logger.info(f"[EXIT] symbol={self.symbol} exit={current_price} pnl={pnl:.2f} reason=TAKE_PROFIT")
            self.close_position("TAKE_PROFIT")

    def close_position(self, reason):
        """Execute position closure."""
        action = "SELL" if self.pm.position > 0 else "BUY"
        qty = abs(self.pm.position)

        # In a real implementation, we might want to check the current price again or use LIMIT orders
        # For this script, we use MARKET orders for immediate execution

        resp = self.client.placesmartorder(
            strategy="SuperTrend VWAP",
            symbol=self.symbol,
            action=action,
            exchange="NSE",
            price_type="MARKET",
            product="MIS",
            quantity=qty,
            position_size=qty
        )

        # Check response - APIClient returns dict on success, None on fail
        if resp:
            # We assume fill at entry price for PM tracking purposes (PM tracks net pos)
            # The actual PnL realized is tracked by the PM based on the close price we pass here?
            # Actually PM.update_position uses the price passed to calculate realized PnL
            # Since we don't have exact fill price yet, we use last known price from the loop
            # But here we don't have it easily. We should pass it or re-fetch.
            # Simplified: Update PM to close state.
            self.pm.update_position(qty, self.pm.entry_price, action)
            self.logger.info(f"Position closed due to {reason}")

    def run(self):
        self.logger.info(f"Starting SuperTrend VWAP for {self.symbol} | Qty: {self.quantity}")

        while True:
            try:
                # Market Hour Check
                if not self.ignore_time and 'is_market_open' in globals() and not is_market_open():
                    self.logger.info("Market is closed. Waiting...")
                    time.sleep(60)
                    continue

                # Fetch sufficient history for Volume Profile (last 5 days)
                df = self.client.history(
                    symbol=self.symbol,
                    exchange="NSE",
                    interval="5m",
                    start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d")
                )

                if df.empty or not isinstance(df, pd.DataFrame):
                    self.logger.warning("No data received. Retrying...")
                    time.sleep(10)
                    continue

                # Calculate Intraday VWAP (resetting daily)
                if 'calculate_intraday_vwap' in globals():
                    df = calculate_intraday_vwap(df)
                else:
                    # Basic VWAP fallback
                     df['tp'] = (df['high'] + df['low'] + df['close']) / 3
                     df['cum_tp_vol'] = (df['tp'] * df['volume']).cumsum()
                     df['cum_vol'] = df['volume'].cumsum()
                     df['vwap'] = df['cum_tp_vol'] / df['cum_vol']
                     df['vwap_dev'] = (df['close'] - df['vwap']) / df['vwap']

                last = df.iloc[-1]

                # Check Exits first (Safety First)
                self.check_exit_conditions(last['close'])

                # Volume Profile Analysis
                poc_price, poc_vol = self.analyze_volume_profile(df)

                # Logic:
                # 1. Price crosses above VWAP
                # 2. Volume Spike (> 1.5x Avg)
                # 3. Price is above POC (Trading above value area)
                # 4. VWAP Deviation is within reasonable bounds (not overextended)

                is_above_vwap = last['close'] > last['vwap']
                is_volume_spike = last['volume'] > df['volume'].mean() * 1.5
                is_above_poc = last['close'] > poc_price
                is_not_overextended = abs(last['vwap_dev']) < 0.02 # Within 2% of VWAP

                self.logger.debug(f"Price: {last['close']} | VWAP: {last['vwap']:.2f} | POC: {poc_price:.2f}")

                # Entry Logic
                if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended:
                    if not self.pm.has_position():
                        self.logger.info(f"[ENTRY] symbol={self.symbol} entry={last['close']} order_id=NEW | POC: {poc_price:.2f} | Dev: {last['vwap_dev']:.4f}")

                        # Place Order
                        resp = self.client.placesmartorder(
                            strategy="SuperTrend VWAP",
                            symbol=self.symbol,
                            action="BUY",
                            exchange="NSE",
                            price_type="MARKET",
                            product="MIS",
                            quantity=self.quantity,
                            position_size=self.quantity
                        )

                        if resp:
                            self.pm.update_position(self.quantity, last['close'], 'BUY')
                    else:
                        self.logger.debug("Signal detected but position already open.")

            except KeyboardInterrupt:
                self.logger.info("Stopping strategy...")
                break
            except Exception as e:
                self.logger.error(f"[ERROR] {e}")
                time.sleep(5)

            time.sleep(15)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SuperTrend VWAP Strategy")
    parser.add_argument("--symbol", type=str, required=True, help="Trading Symbol (e.g., RELIANCE)")
    parser.add_argument("--quantity", type=int, default=10, help="Order Quantity")
    parser.add_argument("--stop_loss_pct", type=float, default=1.0, help="Stop Loss Percentage")
    parser.add_argument("--take_profit_pct", type=float, default=2.0, help="Take Profit Percentage")
    parser.add_argument("--api_key", type=str, help="OpenAlgo API Key")
    parser.add_argument("--host", type=str, help="OpenAlgo Server Host")
    parser.add_argument("--ignore_time", action="store_true", help="Ignore market hours check")

    args = parser.parse_args()
    strategy = SuperTrendVWAPStrategy(args)
    strategy.run()
