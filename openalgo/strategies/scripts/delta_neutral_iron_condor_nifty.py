#!/usr/bin/env python3
"""
Delta Neutral Iron Condor Strategy for NIFTY
Enhanced with Multi-Factor Analysis (VIX, Sentiment, GIFT Nifty)
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root is in path
# Resolves to repo root assuming structure: repo/openalgo/strategies/scripts/this_file.py
project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from openalgo.strategies.utils.trading_utils import APIClient
from openalgo.strategies.utils.option_analytics import calculate_greeks, implied_volatility

# Configuration
SYMBOL = "NIFTY"
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')
HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5002') # Dhan on 5002

# Strategy Parameters
IV_RANK_MIN = 30
IV_RANK_MAX = 70
MIN_DTE = 7
MAX_DTE = 14
SHORT_DELTA_TARGET = 0.20
LONG_DELTA_TARGET = 0.05
MAX_NET_DELTA = 0.10
VIX_MIN_SELL = 20  # Only sell when VIX > 20
STOP_LOSS_MULTIPLIER = 2.0
TARGET_PROFIT_PCT = 0.50

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(f"IC_{SYMBOL}")

class DeltaNeutralIronCondor:
    def __init__(self):
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.positions = {}
        self.market_data = {}

    def fetch_market_context(self):
        """Fetch VIX, Sentiment, etc. (Mocked/Simulated)"""
        # In a real shared environment, this might query a shared DB or Redis
        # For now, we simulate the 'Multi-Factor' inputs
        self.market_data['vix'] = 22.0  # Simulated VIX > 20
        self.market_data['sentiment'] = "Neutral"
        self.market_data['gift_gap'] = 0.2
        self.market_data['iv_rank'] = 55

    def get_option_chain(self):
        """Fetch option chain"""
        # Calculate next expiry (Simplified)
        today = datetime.now()
        days_ahead = 3 - today.weekday()
        if days_ahead <= 0: days_ahead += 7
        next_expiry = (today + timedelta(days=days_ahead)).strftime("%d%b%y").upper()

        # We need a method to get raw chain, APIClient might not have it exposed directly in simple form
        import requests
        url = f"{HOST}/api/v1/optionchain"
        payload = {
            "underlying": SYMBOL,
            "exchange": "NSE_INDEX",
            "expiry_date": next_expiry,
            "strike_count": 30,
            "apikey": API_KEY
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return data
        except Exception as e:
            logger.error(f"Error fetching chain: {e}")
        return None

    def select_strikes_by_delta(self, chain_data):
        """Select strikes based on Real Delta Calculation"""
        if not chain_data: return None

        spot = chain_data.get('underlying_ltp', 0)
        if spot == 0: return None

        T = 4.0 / 365.0 # Approx
        r = 0.06

        strikes = {'short_ce': None, 'long_ce': None, 'short_pe': None, 'long_pe': None}
        min_diff_short_ce = 1.0
        min_diff_long_ce = 1.0
        min_diff_short_pe = 1.0
        min_diff_long_pe = 1.0

        for item in chain_data['chain']:
            strike = item['strike']

            # Call Delta
            ce_ltp = item['ce'].get('ltp', 0)
            if ce_ltp > 0:
                iv_ce = implied_volatility(ce_ltp, spot, strike, T, r, 'ce')
                greeks_ce = calculate_greeks(spot, strike, T, r, iv_ce, 'ce')
                delta_ce = greeks_ce['delta']

                # Check Short CE (Target 0.20)
                if abs(delta_ce - SHORT_DELTA_TARGET) < min_diff_short_ce:
                    min_diff_short_ce = abs(delta_ce - SHORT_DELTA_TARGET)
                    strikes['short_ce'] = item

                # Check Long CE (Target 0.05)
                if abs(delta_ce - LONG_DELTA_TARGET) < min_diff_long_ce:
                    min_diff_long_ce = abs(delta_ce - LONG_DELTA_TARGET)
                    strikes['long_ce'] = item

            # Put Delta
            pe_ltp = item['pe'].get('ltp', 0)
            if pe_ltp > 0:
                iv_pe = implied_volatility(pe_ltp, spot, strike, T, r, 'pe')
                greeks_pe = calculate_greeks(spot, strike, T, r, iv_pe, 'pe')
                delta_pe = abs(greeks_pe['delta']) # Put delta is negative

                # Check Short PE (Target 0.20)
                if abs(delta_pe - SHORT_DELTA_TARGET) < min_diff_short_pe:
                    min_diff_short_pe = abs(delta_pe - SHORT_DELTA_TARGET)
                    strikes['short_pe'] = item

                # Check Long PE (Target 0.05)
                if abs(delta_pe - LONG_DELTA_TARGET) < min_diff_long_pe:
                    min_diff_long_pe = abs(delta_pe - LONG_DELTA_TARGET)
                    strikes['long_pe'] = item

        if all(strikes.values()):
            expiry = chain_data.get('expiry_date', '29JAN26') # Fallback if missing
            return {
                "short_ce": f"{SYMBOL}{expiry}{strikes['short_ce']['strike']}CE",
                "long_ce": f"{SYMBOL}{expiry}{strikes['long_ce']['strike']}CE",
                "short_pe": f"{SYMBOL}{expiry}{strikes['short_pe']['strike']}PE",
                "long_pe": f"{SYMBOL}{expiry}{strikes['long_pe']['strike']}PE"
            }
        return None

    def check_filters(self):
        """Check entry filters"""
        # 1. VIX Filter
        if self.market_data['vix'] < VIX_MIN_SELL:
            logger.info(f"VIX {self.market_data['vix']} too low for selling (Min {VIX_MIN_SELL})")
            return False

        # 2. Sentiment Filter
        if self.market_data['sentiment'] == "Negative":
            logger.info("Negative sentiment, skipping new entries")
            return False

        return True

    def place_iron_condor(self, strikes):
        """Place the 4-leg order"""
        logger.info(f"Placing Iron Condor: {strikes}")
        # In a real execution, we would iterate and place orders
        # self.api_client.placesmartorder(...)
        # For now, just log
        logger.info("Orders sent (Simulated)")

    def manage_positions(self):
        """Monitor and adjust positions (Placeholder)"""
        # Logic to check stop loss, profit target, etc.
        pass

    def run(self):
        logger.info(f"Starting Delta Neutral Iron Condor for {SYMBOL} (Continuous Mode)")
        while True:
            try:
                self.fetch_market_context()

                if not self.positions:
                    if self.check_filters():
                        chain = self.get_option_chain()
                        if chain:
                            strikes = self.select_strikes_by_delta(chain)
                            if strikes:
                                self.place_iron_condor(strikes)
                                # self.positions = strikes # Mark as active
                            else:
                                logger.warning("Could not find suitable strikes")
                        else:
                            logger.warning("Could not fetch option chain (API offline?)")
                    else:
                        logger.info("Filters not passed")
                else:
                    self.manage_positions()

            except Exception as e:
                logger.error(f"Strategy Error: {e}")

            # Wait 15 minutes
            time.sleep(900)

if __name__ == "__main__":
    strategy = DeltaNeutralIronCondor()
    strategy.run()
