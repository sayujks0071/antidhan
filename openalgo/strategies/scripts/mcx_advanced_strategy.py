#!/usr/bin/env python3
"""
MCX Advanced Commodity Strategy
Analyzes MCX market data using OpenAlgo API and executes strategies
based on multi-factor analysis (Trend, Momentum, Global Alignment).
"""

import os
import sys
import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Ensure repo root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.trading_utils import APIClient
    import yfinance as yf # Optional
except ImportError:
    pass

# Configuration
API_KEY = os.getenv('OPENALGO_APIKEY')
HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001') # Kite on 5001 often used for equities, check port
# Note: Memory says Kite 5001, Dhan 5002. MCX is usually on Kite or Dhan. Let's default to Kite port for now or use env.

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MCX_Advanced")

class MCXAdvancedStrategy:
    def __init__(self):
        self.api_key = API_KEY
        if not self.api_key:
            logger.warning("OPENALGO_APIKEY not set. API calls will fail.")

        self.client = None
        if 'APIClient' in globals():
            self.client = APIClient(api_key=self.api_key, host=HOST)

        self.market_context = {
            'usd_inr': {'price': 83.0, 'trend': 'Neutral', 'change': 0.0},
            'global_commodities': {}
        }
        self.opportunities = []

        # Symbol Mapping: Generic -> Tradable Symbol (Update monthly)
        # Assuming current month futures
        self.ticker_map = {
            'GOLD': {'global': 'GC=F', 'tradable': 'GOLD24DECFUT'}, # Example
            'SILVER': {'global': 'SI=F', 'tradable': 'SILVER24DECFUT'},
            'CRUDEOIL': {'global': 'CL=F', 'tradable': 'CRUDEOIL24NOVFUT'},
            'NATURALGAS': {'global': 'NG=F', 'tradable': 'NATURALGAS24NOVFUT'},
            'COPPER': {'global': 'HG=F', 'tradable': 'COPPER24NOVFUT'}
        }

    def fetch_global_data(self):
        """Fetch global commodity prices and USD/INR."""
        logger.info("Fetching global market context...")
        if 'yf' in globals():
            try:
                # USD/INR
                usd = yf.Ticker("INR=X")
                hist = usd.history(period="5d")
                if not hist.empty:
                    current = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2]
                    change = (current - prev) / prev * 100
                    self.market_context['usd_inr'] = {
                        'price': round(current, 2),
                        'trend': "Up" if change > 0 else "Down",
                        'change': round(change, 2)
                    }

                # Global Commodities
                for sym, details in self.ticker_map.items():
                    try:
                        t = yf.Ticker(details['global'])
                        h = t.history(period="5d")
                        if not h.empty:
                            curr = h['Close'].iloc[-1]
                            prev = h['Close'].iloc[-2]
                            self.market_context['global_commodities'][sym] = {
                                'price': curr,
                                'change': round((curr - prev)/prev*100, 2)
                            }
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Global data fetch error: {e}")

    def fetch_mcx_data(self, symbol_key):
        """Fetch MCX data using APIClient."""
        if not self.client:
            return pd.DataFrame() # Return empty if no client

        tradable_symbol = self.ticker_map[symbol_key]['tradable']

        # Fetch 5 days of 15m data
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

        df = self.client.history(symbol=tradable_symbol, exchange="MCX", interval="15m",
                                 start_date=start_date, end_date=end_date)

        if isinstance(df, pd.DataFrame) and not df.empty:
            return df

        logger.warning(f"No data for {tradable_symbol}")
        return pd.DataFrame()

    def calculate_indicators(self, df):
        """Calculate basic indicators."""
        if df.empty: return df

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # ATR
        df['tr'] = np.maximum(df['high'] - df['low'],
                              np.maximum(abs(df['high'] - df['close'].shift(1)),
                                         abs(df['low'] - df['close'].shift(1))))
        df['atr'] = df['tr'].rolling(window=14).mean()

        return df

    def analyze(self):
        """Analyze markets."""
        for sym in self.ticker_map:
            df = self.fetch_mcx_data(sym)
            if df.empty: continue

            df = self.calculate_indicators(df)
            last = df.iloc[-1]

            # Simple Logic: Trend + Global Alignment
            # If RSI > 50 and Global is Up -> Buy

            global_change = self.market_context['global_commodities'].get(sym, {}).get('change', 0)
            score = 50

            if last['rsi'] > 55: score += 20
            if last['rsi'] < 45: score -= 20

            if global_change > 0.5: score += 10
            if global_change < -0.5: score -= 10

            action = "HOLD"
            if score > 70: action = "BUY"
            elif score < 30: action = "SELL"

            self.opportunities.append({
                'symbol': sym,
                'tradable': self.ticker_map[sym]['tradable'],
                'score': score,
                'action': action,
                'price': last['close']
            })

            logger.info(f"{sym}: Score {score} | Action {action} | Price {last['close']}")

    def execute_trades(self):
        """Execute top trades."""
        if not self.client: return

        for opp in self.opportunities:
            if opp['action'] in ["BUY", "SELL"]:
                logger.info(f"Executing {opp['action']} for {opp['symbol']} ({opp['tradable']})")
                self.client.placesmartorder(
                    strategy="MCX_Advanced",
                    symbol=opp['tradable'],
                    action=opp['action'],
                    exchange="MCX",
                    price_type="MARKET",
                    product="NRML",
                    quantity=1, # Default 1 lot
                    position_size=1
                )
                time.sleep(1)

    def run(self):
        self.fetch_global_data()
        self.analyze()
        self.execute_trades()

if __name__ == "__main__":
    bot = MCXAdvancedStrategy()
    bot.run()
