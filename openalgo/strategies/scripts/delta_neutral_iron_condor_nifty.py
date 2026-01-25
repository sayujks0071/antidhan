#!/usr/bin/env python3
"""
Delta Neutral Iron Condor Strategy for NIFTY
Enhanced with Multi-Factor Analysis (VIX, Sentiment, GIFT Nifty)
"""
import os
import time
import logging
import requests
from datetime import datetime, timedelta

try:
    from openalgo import api
except ImportError:
    api = None

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
VIX_MIN_SELL = 20  # Only sell when VIX > 20 (Enhanced)
STOP_LOSS_MULTIPLIER = 2.0
TARGET_PROFIT_PCT = 0.50

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(f"IC_{SYMBOL}")

class DeltaNeutralIronCondor:
    def __init__(self):
        self.api_client = None
        if api:
            self.api_client = api(api_key=API_KEY, host=HOST)
        self.positions = {}
        self.market_data = {}

    def _post(self, endpoint, payload):
        """Helper for direct API calls to endpoints not covered by client"""
        url = f"{HOST}{endpoint}"
        try:
            if 'apikey' not in payload:
                payload['apikey'] = API_KEY
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"API Error {endpoint}: {e}")
        return None

    def fetch_market_context(self):
        """Fetch VIX, Sentiment, etc."""
        # Mocking external data for strategy logic
        # In production, integrate with real feeds
        self.market_data['vix'] = 22.0  # Mock > 20 for test
        self.market_data['sentiment'] = "Neutral"
        self.market_data['gift_gap'] = 0.2 # 0.2% gap up

    def get_option_chain(self):
        """Fetch option chain with greeks"""
        next_expiry = (datetime.now() + timedelta(days=7)).strftime("%d%b%y").upper() # Simplified expiry logic
        payload = {
            "underlying": SYMBOL,
            "exchange": "NSE_INDEX",
            "expiry_date": next_expiry,
            "strike_count": 20
        }
        return self._post('/api/v1/optionchain', payload)

    def select_strikes(self, chain_data):
        """Select strikes based on Delta and VIX"""
        if not chain_data or chain_data.get('status') != 'success':
            return None

        # Sort chain by strike
        chain = sorted(chain_data['chain'], key=lambda x: x['strike'])

        # Calculate/Fetch Greeks for each strike (Mocking delta here for selection logic)
        # In real usage, chain_data should contain greeks or we call optiongreeks

        # Finding Short Strikes (~20 Delta)
        # Finding Long Strikes (~5 Delta)

        # Simplified selection logic for demonstration without real greeks stream
        spot = chain_data.get('underlying_ltp', 0)
        if spot == 0: return None

        # Adjust for GIFT Nifty Gap if significant
        gap_bias = 0
        if self.market_data['gift_gap'] > 0.5:
            gap_bias = 50 # Shift strikes up
        elif self.market_data['gift_gap'] < -0.5:
            gap_bias = -50

        # Construct Strikes
        short_ce_strike = int(round(spot * 1.02 / 50) * 50) + gap_bias
        long_ce_strike = int(round(spot * 1.05 / 50) * 50) + gap_bias
        short_pe_strike = int(round(spot * 0.98 / 50) * 50) + gap_bias
        long_pe_strike = int(round(spot * 0.95 / 50) * 50) + gap_bias

        return {
            "short_ce": f"{SYMBOL}{chain_data['expiry_date']}{short_ce_strike}CE",
            "long_ce": f"{SYMBOL}{chain_data['expiry_date']}{long_ce_strike}CE",
            "short_pe": f"{SYMBOL}{chain_data['expiry_date']}{short_pe_strike}PE",
            "long_pe": f"{SYMBOL}{chain_data['expiry_date']}{long_pe_strike}PE"
        }

    def check_filters(self):
        """Check entry filters"""
        # 1. VIX Filter
        if self.market_data['vix'] < VIX_MIN_SELL:
            logger.info(f"VIX {self.market_data['vix']} too low for selling (Min {VIX_MIN_SELL})")
            return False

        # 2. Sentiment Filter
        if self.market_data['sentiment'] == "Negative":
            # Avoid selling puts if sentiment is very negative?
            # Or just reduce size. For now, we skip if extreme.
            logger.info("Negative sentiment, skipping new entries")
            return False

        return True

    def place_iron_condor(self, strikes):
        """Place the 4-leg order"""
        logger.info(f"Placing Iron Condor: {strikes}")
        # Use api_client.place_order for each leg
        if not self.api_client:
            logger.warning("No API client, skipping order placement")
            return

        # Sell Short Legs
        # Buy Long Legs
        # This is where actual execution happens
        pass

    def manage_positions(self):
        """Monitor and adjust positions"""
        # Check P&L
        # Check Delta (Hedge if > 0.15)
        # Check VIX spike (Stop loss)
        pass

    def run(self):
        logger.info(f"Starting Delta Neutral Iron Condor for {SYMBOL}")
        while True:
            try:
                self.fetch_market_context()

                if not self.positions:
                    if self.check_filters():
                        chain = self.get_option_chain()
                        strikes = self.select_strikes(chain)
                        if strikes:
                            self.place_iron_condor(strikes)
                            # Update positions state
                else:
                    self.manage_positions()

            except Exception as e:
                logger.error(f"Strategy Loop Error: {e}")

            time.sleep(60) # Run every minute

if __name__ == "__main__":
    strategy = DeltaNeutralIronCondor()
    strategy.run()
