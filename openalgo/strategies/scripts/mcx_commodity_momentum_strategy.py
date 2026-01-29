import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# Add repo root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.trading_utils import APIClient
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    APIClient = None
    SymbolResolver = None

# Configuration
SYMBOL = os.getenv('SYMBOL', 'GOLDM05FEB26FUT')
API_HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')

# Strategy Parameters (Can be injected or default)
PARAMS = {
    'period_adx': 14,
    'period_rsi': 14,
    'period_atr': 14,
    'adx_threshold': 25,
    'rsi_overbought': 70,
    'rsi_oversold': 30,
    'use_global_filter': False,
    'use_seasonality': False,
    'risk_per_trade': 0.02, # 2% of capital
}

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(f"MCX_Momentum_{SYMBOL}")

class MCXMomentumStrategy:
    def __init__(self, symbol, params):
        self.symbol = symbol
        self.params = params
        self.position = 0
        self.data = pd.DataFrame()

    def fetch_data(self):
        """Fetch live or historical data from OpenAlgo."""
        try:
            # Simulated data fetching
            # response = requests.get(f"{API_HOST}/api/history?symbol={self.symbol}&interval=15m")
            # if response.status_code == 200:
            #     self.data = pd.DataFrame(response.json())

            # Mocking data for structure
            logger.info(f"Fetching data for {self.symbol}...")
            dates = pd.date_range(end=datetime.now(), periods=100, freq='15min')
            self.data = pd.DataFrame({
                'open': np.random.uniform(100, 200, 100),
                'high': np.random.uniform(100, 200, 100),
                'low': np.random.uniform(100, 200, 100),
                'close': np.random.uniform(100, 200, 100),
                'volume': np.random.randint(1000, 10000, 100)
            }, index=dates)

            # Ensure high/low consistency
            self.data['high'] = self.data[['open', 'close', 'high']].max(axis=1)
            self.data['low'] = self.data[['open', 'close', 'low']].min(axis=1)

        except Exception as e:
            logger.error(f"Error fetching data: {e}")

    def calculate_indicators(self):
        """Calculate technical indicators."""
        if self.data.empty:
            return

        df = self.data

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.params['period_rsi']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params['period_rsi']).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(window=self.params['period_atr']).mean()

        # ADX (Simplified)
        df['adx'] = np.random.uniform(10, 50, len(df)) # Placeholder for complex ADX calc

        self.data = df

    def check_signals(self):
        """Check entry and exit conditions."""
        if self.data.empty:
            return

        current = self.data.iloc[-1]
        prev = self.data.iloc[-2]

        # Global Filter Check (Mock)
        global_alignment = True
        if self.params['use_global_filter']:
            # Fetch global trend and compare
            # if global_trend != current_trend: global_alignment = False
            pass

        # Entry Logic
        if self.position == 0:
            if (current['adx'] > self.params['adx_threshold'] and
                current['rsi'] > 50 and
                current['close'] > prev['close'] and
                global_alignment):

                self.entry("BUY", current['close'])

            elif (current['adx'] > self.params['adx_threshold'] and
                  current['rsi'] < 50 and
                  current['close'] < prev['close'] and
                  global_alignment):

                self.entry("SELL", current['close'])

        # Exit Logic
        elif self.position > 0: # Long
            if current['close'] < prev['low']: # Simple trailing stop
                self.exit("SELL", current['close'])

        elif self.position < 0: # Short
            if current['close'] > prev['high']:
                self.exit("BUY", current['close'])

    def entry(self, side, price):
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f}")
        # Execute trade via API
        # requests.post(f"{API_HOST}/api/orders", json={...})
        self.position = 1 if side == "BUY" else -1

    def exit(self, side, price):
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f}")
        # Execute trade via API
        self.position = 0

    def run(self):
        logger.info(f"Starting MCX Momentum Strategy for {self.symbol}")
        while True:
            self.fetch_data()
            self.calculate_indicators()
            self.check_signals()
            time.sleep(900) # 15 minutes

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MCX Commodity Momentum Strategy')
    parser.add_argument('--symbol', type=str, help='MCX Symbol (e.g., GOLDM05FEB26FUT)')
    parser.add_argument('--port', type=int, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')
    args = parser.parse_args()
    if args.symbol:
        SYMBOL = args.symbol
    elif os.getenv('SYMBOL'):
        SYMBOL = os.getenv('SYMBOL')
    if args.port:
        API_HOST = f"http://127.0.0.1:{args.port}"
    elif os.getenv('OPENALGO_PORT'):
        API_HOST = f"http://127.0.0.1:{os.getenv('OPENALGO_PORT')}"
    if args.api_key:
        API_KEY = args.api_key
    else:
        API_KEY = os.getenv('OPENALGO_APIKEY', API_KEY)
    if SYMBOL == "REPLACE_ME":
        logger.error(f"❌ Symbol not configured! SYMBOL={SYMBOL}")
        logger.error("Please set SYMBOL environment variable or use --symbol argument")
        exit(1)
    strategy = MCXMomentumStrategy(SYMBOL, PARAMS)
    strategy.run()
