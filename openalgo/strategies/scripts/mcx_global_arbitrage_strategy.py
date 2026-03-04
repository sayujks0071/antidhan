import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Try importing dependencies
try:
    import yfinance as yf
except ImportError:
    print("Warning: yfinance not found. Global market data will be limited.")
    yf = None

try:
    from strategy_preamble import BaseStrategy
except ImportError:
    import sys, os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
    from base_strategy import BaseStrategy

# Configuration defaults
DEFAULT_GLOBAL_SYMBOL = os.getenv('GLOBAL_SYMBOL', 'GC=F') # Default to Gold Futures

class MCXGlobalArbitrageStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.global_symbol = kwargs.get('global_symbol', DEFAULT_GLOBAL_SYMBOL)
        self.divergence_threshold = float(kwargs.get('divergence_threshold', 3.0))
        self.convergence_threshold = float(kwargs.get('convergence_threshold', 1.5))
        self.lookback_period = int(kwargs.get('lookback_period', 20))

        self.data = pd.DataFrame()
        self.last_trade_time = 0
        self.cooldown_seconds = 300

        # Session Reference Points (Opening Price of the session/day)
        self.session_ref_mcx = None
        self.session_ref_global = None

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--global_symbol', type=str, default=DEFAULT_GLOBAL_SYMBOL, help='Global Symbol for comparison (e.g. GC=F)')
        parser.add_argument('--divergence_threshold', type=float, default=3.0, help='Divergence Threshold')
        parser.add_argument('--convergence_threshold', type=float, default=1.5, help='Convergence Threshold')
        parser.add_argument('--lookback_period', type=int, default=20, help='Lookback Period')

    def fetch_data(self):
        """Fetch live MCX and Global prices. Returns True on success."""
        if not self.client:
            self.logger.error("❌ CRITICAL: No API client available. Strategy requires API client.")
            return False
        
        try:
            self.logger.info(f"Fetching data for {self.symbol} vs {self.global_symbol}...")

            # 1. Fetch MCX Price from Kite API
            mcx_quote = self.client.get_quote(self.symbol, exchange="MCX")
            
            if not mcx_quote or 'ltp' not in mcx_quote:
                self.logger.warning(f"Failed to fetch MCX price for {self.symbol}. Retrying...")
                return False
            
            mcx_price = float(mcx_quote['ltp'])

            # 2. Fetch Global Price
            global_price = None
            
            # Try fetching from Kite if it looks like a Kite symbol (no '=')
            if '=' not in self.global_symbol:
                try:
                    global_quote = self.client.get_quote(self.global_symbol, exchange="MCX") # Or other exchange
                    if global_quote and 'ltp' in global_quote:
                        global_price = float(global_quote['ltp'])
                except Exception:
                    pass
            
            # Fallback to yfinance
            if global_price is None and yf:
                try:
                    ticker = yf.Ticker(self.global_symbol)
                    # Get fast price
                    hist = ticker.history(period="1d")
                    if not hist.empty:
                        global_price = hist['Close'].iloc[-1]
                except Exception as e:
                    self.logger.warning(f"Failed to fetch global price from yfinance: {e}")

            if global_price is None:
                self.logger.warning(f"Could not fetch global price for {self.global_symbol}")
                return False

            current_time = datetime.now()

            # Initialize Session Reference if None (First run of the day)
            if self.session_ref_mcx is None:
                self.session_ref_mcx = mcx_price
                self.session_ref_global = global_price
                self.logger.info(f"Session Start Reference: MCX={mcx_price}, Global={global_price}")

            new_row = pd.DataFrame({
                'timestamp': [current_time],
                'mcx_price': [mcx_price],
                'global_price': [global_price]
            })

            self.data = pd.concat([self.data, new_row], ignore_index=True)
            if len(self.data) > 100:
                self.data = self.data.iloc[-100:]

            return True

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}", exc_info=True)
            return False

    def cycle(self):
        """Check for arbitrage opportunities using Percentage Change Divergence."""
        if not self.fetch_data():
            return

        if self.data.empty or self.session_ref_mcx is None:
            return

        current = self.data.iloc[-1]

        # Calculate Percentage Change from Session Start
        mcx_change_pct = ((current['mcx_price'] - self.session_ref_mcx) / self.session_ref_mcx) * 100
        global_change_pct = ((current['global_price'] - self.session_ref_global) / self.session_ref_global) * 100

        # Divergence: If MCX rose more than Global, it's overpriced relative to start
        divergence_pct = mcx_change_pct - global_change_pct

        self.logger.info(f"MCX Chg: {mcx_change_pct:.2f}% | Global Chg: {global_change_pct:.2f}% | Divergence: {divergence_pct:.2f}%")
        
        # Entry Logic
        current_time = time.time()
        time_since_last_trade = current_time - self.last_trade_time
        
        has_pos = self.pm and self.pm.has_position()

        if not has_pos:
            if time_since_last_trade < self.cooldown_seconds:
                return
            
            # MCX is Overpriced -> Sell MCX
            if divergence_pct > self.divergence_threshold:
                qty = self.get_adaptive_quantity(current['mcx_price'])
                self.sell(qty, current['mcx_price'], "HIGH")
                self.last_trade_time = time.time()

            # MCX is Underpriced -> Buy MCX
            elif divergence_pct < -self.divergence_threshold:
                qty = self.get_adaptive_quantity(current['mcx_price'])
                self.buy(qty, current['mcx_price'], "HIGH")
                self.last_trade_time = time.time()

        # Exit Logic
        else:
            abs_div = abs(divergence_pct)
            if abs_div < self.convergence_threshold:
                qty = abs(self.pm.position)
                if self.pm.position < 0:
                    self.buy(qty, current['mcx_price'], "HIGH")
                else:
                    self.sell(qty, current['mcx_price'], "HIGH")
                self.last_trade_time = time.time()

if __name__ == "__main__":
    MCXGlobalArbitrageStrategy.cli()
