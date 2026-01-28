import os
import time
import logging
import argparse
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# Configuration
SYMBOL = "REPLACE_ME"
GLOBAL_SYMBOL = "REPLACE_ME_GLOBAL"
API_HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')

# Strategy Parameters
PARAMS = {
    'divergence_threshold': 3.0, # Percent
    'convergence_threshold': 0.5, # Percent
    'lookback_period': 20,
}

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(f"MCX_Arbitrage_{SYMBOL}")

class MCXGlobalArbitrageStrategy:
    def __init__(self, symbol, global_symbol, params):
        self.symbol = symbol
        self.global_symbol = global_symbol
        self.params = params
        self.position = 0
        self.data = pd.DataFrame()

    def fetch_data(self):
        """Fetch live MCX and Global prices."""
        try:
            # Mocking data
            logger.info(f"Fetching data for {self.symbol} vs {self.global_symbol}...")

            # Simulate MCX Price
            mcx_price = 50000 + np.random.normal(0, 100)

            # Simulate Global Price (converted to INR)
            # Sometimes create a divergence
            divergence_factor = 1.0
            if np.random.random() > 0.8:
                divergence_factor = 1.05 # 5% divergence

            global_price = mcx_price * divergence_factor + np.random.normal(0, 50)

            current_time = datetime.now()

            new_row = pd.DataFrame({
                'timestamp': [current_time],
                'mcx_price': [mcx_price],
                'global_price': [global_price]
            })

            self.data = pd.concat([self.data, new_row], ignore_index=True)
            if len(self.data) > 100:
                self.data = self.data.iloc[-100:]

        except Exception as e:
            logger.error(f"Error fetching data: {e}")

    def check_signals(self):
        """Check for arbitrage opportunities."""
        if self.data.empty:
            return

        current = self.data.iloc[-1]

        # Calculate Divergence %
        diff = current['mcx_price'] - current['global_price']
        divergence_pct = (diff / current['global_price']) * 100

        logger.info(f"Divergence: {divergence_pct:.2f}% (MCX: {current['mcx_price']:.2f}, Global: {current['global_price']:.2f})")

        # Entry Logic
        if self.position == 0:
            # MCX is Overpriced -> Sell MCX
            if divergence_pct > self.params['divergence_threshold']:
                self.entry("SELL", current['mcx_price'], f"MCX Premium > {self.params['divergence_threshold']}%")

            # MCX is Underpriced -> Buy MCX
            elif divergence_pct < -self.params['divergence_threshold']:
                self.entry("BUY", current['mcx_price'], f"MCX Discount > {self.params['divergence_threshold']}%")

        # Exit Logic
        elif self.position != 0:
            # Check for convergence
            abs_div = abs(divergence_pct)
            if abs_div < self.params['convergence_threshold']:
                side = "BUY" if self.position == -1 else "SELL"
                self.exit(side, current['mcx_price'], "Convergence reached")

    def entry(self, side, price, reason):
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Reason: {reason}")
        self.position = 1 if side == "BUY" else -1

    def exit(self, side, price, reason):
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Reason: {reason}")
        self.position = 0

    def run(self):
        logger.info(f"Starting MCX Global Arbitrage Strategy for {self.symbol}")
        while True:
            self.fetch_data()
            self.check_signals()
            time.sleep(60) # Check every minute for arbitrage

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MCX Global Arbitrage Strategy')
    parser.add_argument('--port', type=int, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    args = parser.parse_args()

    if args.port:
        API_HOST = f"http://127.0.0.1:{args.port}"
    if args.api_key:
        API_KEY = args.api_key

    strategy = MCXGlobalArbitrageStrategy(SYMBOL, GLOBAL_SYMBOL, PARAMS)
    strategy.run()
