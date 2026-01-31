#!/usr/bin/env python3
import sys
import os
import argparse
import logging
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
from openalgo.strategies.utils.option_analytics import calculate_greeks, calculate_max_pain

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(project_root / "openalgo" / "strategies" / "logs" / "iron_condor.log")
    ]
)
logger = logging.getLogger("DeltaNeutralIronCondor")

class DeltaNeutralIronCondor:
    def __init__(self, api_client, symbol="NIFTY", qty=50, max_vix=30):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.max_vix = max_vix
        self.pm = PositionManager(f"{symbol}_IC")

    def get_vix(self):
        q = self.client.get_quote("INDIA VIX", "NSE")
        return float(q['ltp']) if q else 15.0

    def select_strikes(self, spot, vix, chain_data):
        """
        Select strikes based on Delta and VIX.
        Higher VIX -> Wider Wings (Lower Delta for Shorts?)
        Actually, High VIX means we can sell further OTM for same premium.
        """
        # Calculate Max Pain
        max_pain = calculate_max_pain(chain_data)
        logger.info(f"Max Pain Strike: {max_pain}")

        # Use Max Pain as center if close to Spot (within 1%)
        center_price = spot
        if max_pain and abs(spot - max_pain) < (spot * 0.01):
            logger.info("Using Max Pain as Center Price for Strike Selection")
            center_price = max_pain

        # Target Delta for Shorts
        target_delta = 0.20

        # Adjust Wing Width based on VIX
        # Base width 200 for NIFTY
        wing_width = 200
        if vix > 20:
            wing_width = 400
        elif vix < 12:
            wing_width = 100

        logger.info(f"VIX: {vix} -> Wing Width: {wing_width}")

        # Delta-Based Selection Logic
        ce_short = None
        pe_short = None

        # Try to find strikes with Delta ~ 0.20
        # If chain_data is available and has 'delta' or needed params
        try:
            strikes = sorted([item for item in chain_data if 'strike' in item], key=lambda x: x['strike'])

            best_ce_diff = 1.0
            best_pe_diff = 1.0

            # Assumptions
            T = 7/365.0 # 7 days to expiry (Weekly)
            r = 0.06    # Risk Free Rate

            for item in strikes:
                strike = item['strike']

                # Helper to get IV
                def get_iv(itm, type_key):
                    # Try flattened first
                    iv = itm.get(f'{type_key}_iv', 0)
                    if iv == 0:
                        # Try nested
                        iv = itm.get(type_key, {}).get('iv', 0)

                    if iv > 0:
                         # Assume IV is percentage (e.g., 20.0), convert to decimal
                         return iv / 100.0
                    return vix / 100.0

                # Calculate Call Delta
                iv_ce = get_iv(item, 'ce')
                ce_greeks = calculate_greeks(spot, strike, T, r, iv_ce, 'ce')
                ce_delta = ce_greeks.get('delta', 0.5)

                # We want Call Delta ~ 0.20 (OTM Call)
                # Ensure strike > spot for OTM Call logic check
                if strike > spot and abs(ce_delta - target_delta) < best_ce_diff:
                    best_ce_diff = abs(ce_delta - target_delta)
                    ce_short = strike

                # Calculate Put Delta
                iv_pe = get_iv(item, 'pe')
                pe_greeks = calculate_greeks(spot, strike, T, r, iv_pe, 'pe')
                pe_delta = abs(pe_greeks.get('delta', -0.5)) # Put Delta is negative

                # We want Put Delta ~ 0.20 (OTM Put)
                # Ensure strike < spot for OTM Put logic check
                if strike < spot and abs(pe_delta - target_delta) < best_pe_diff:
                    best_pe_diff = abs(pe_delta - target_delta)
                    pe_short = strike

            logger.info(f"Delta Search Results: CE Short {ce_short} (Diff: {best_ce_diff:.4f}), PE Short {pe_short} (Diff: {best_pe_diff:.4f})")

        except Exception as e:
            logger.error(f"Delta calculation failed: {e}")
            ce_short = None
            pe_short = None

        # Fallback to ATM + Width if Delta search failed or not enough data
        atm = round(center_price / 50) * 50

        if not ce_short:
            ce_short = atm + wing_width
        if not pe_short:
            pe_short = atm - wing_width

        # Longs (Wings)
        ce_long = ce_short + wing_width
        pe_long = pe_short - wing_width

        return {
            "ce_short": ce_short,
            "pe_short": pe_short,
            "ce_long": ce_long,
            "pe_long": pe_long
        }

    def execute(self):
        logger.info(f"Starting execution for {self.symbol}")

        if not is_market_open():
             logger.warning("Market is closed.")
             # return # Allow running for testing/mocking

        vix = self.get_vix()
        logger.info(f"Current VIX: {vix}")

        # Filter: Only Sell Premium if VIX > 20 (as requested)
        if vix < 20:
            logger.warning(f"VIX {vix} < 20. Market conditions not suitable for selling premium (Iron Condor). Skipping.")
            return

        if vix > self.max_vix:
            logger.warning(f"VIX {vix} > {self.max_vix}. Reducing Quantity by 50%.")
            self.qty = int(self.qty * 0.5)

        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        spot = float(quote['ltp']) if quote else 0
        if spot == 0:
            logger.error("Could not fetch spot price.")
            return

        logger.info(f"Spot: {spot}")

        # Fetch Chain
        chain = self.client.get_option_chain(self.symbol)

        strikes = self.select_strikes(spot, vix, chain)
        logger.info(f"Selected Strikes: {strikes}")

        # Place Orders (Mock)
        # Sell Shorts, Buy Longs
        logger.info(f"Placing orders for {self.qty} qty...")

        # Example calls
        # self.client.placesmartorder(...)
        logger.info("Strategy execution completed (Simulation).")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    client = APIClient(api_key=os.getenv("OPENALGO_API_KEY"), host=f"http://127.0.0.1:{args.port}")
    strategy = DeltaNeutralIronCondor(client, args.symbol, args.qty)
    strategy.execute()

if __name__ == "__main__":
    main()
