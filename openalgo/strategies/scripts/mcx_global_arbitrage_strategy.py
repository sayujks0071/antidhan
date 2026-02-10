#!/usr/bin/env python3
"""
MCX Global Arbitrage Strategy
Tracks price divergence between MCX and Global markets (e.g. Gold Futures vs Spot Gold).
Refactored to use BaseStrategy.
"""
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

# Add repo root to path to allow imports (if running as script)
try:
    from base_strategy import BaseStrategy
except ImportError:
    # Try setting path to find utils
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy

class MCXGlobalArbitrageStrategy(BaseStrategy):
    def __init__(self, symbol, quantity=1, api_key=None, host=None, ignore_time=False,
                 log_file=None, client=None, **kwargs):

        super().__init__(
            name="MCX_Global_Arbitrage",
            symbol=symbol,
            quantity=quantity,
            exchange="MCX",
            api_key=api_key,
            host=host,
            ignore_time=ignore_time,
            log_file=log_file,
            client=client,
            **kwargs
        )

        # Strategy Parameters
        self.params = {
            'divergence_threshold': 3.0, # Percent
            'convergence_threshold': 1.5, # Percent
            'lookback_period': 20,
            'global_symbol': 'GC=F'
        }
        self.params.update(kwargs)

        # State
        self.data = pd.DataFrame()
        self.last_trade_time = 0
        self.cooldown_seconds = 300
        self.session_ref_mcx = None
        self.session_ref_global = None

        self.global_symbol = self.params.get('global_symbol', 'GC=F')
        self.logger.info(f"Initialized Strategy for {symbol} vs {self.global_symbol}")

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--global_symbol', type=str, default='GC=F', help='Global Symbol for comparison (e.g. GC=F)')
        parser.add_argument('--port', type=int, help='API Port')
        parser.add_argument('--divergence_threshold', type=float, default=3.0, help='Divergence Threshold %')
        parser.add_argument('--underlying', type=str, help='Commodity Name (e.g., GOLD, SILVER)') # Handled by BaseStrategy logic?

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        if args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"

        kwargs['global_symbol'] = args.global_symbol
        kwargs['divergence_threshold'] = args.divergence_threshold

        return kwargs

    def fetch_data(self):
        """Fetch live MCX and Global prices. Returns True on success."""
        if not self.client:
            self.logger.error("❌ CRITICAL: No API client available. Strategy requires API client.")
            return False
        
        try:
            self.logger.info(f"Fetching data for {self.symbol} vs {self.global_symbol}...")

            # 1. Fetch MCX Price from Kite API via BaseStrategy's client
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
                    global_quote = self.client.get_quote(self.global_symbol, exchange="MCX")
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
        """Main execution cycle called by BaseStrategy.run"""
        if self.fetch_data():
            self.check_signals()

    def check_signals(self):
        """Check for arbitrage opportunities using Percentage Change Divergence."""
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
        
        # Determine position from PositionManager
        current_pos = 0
        if self.pm:
            current_pos = self.pm.position

        if current_pos == 0:
            if time_since_last_trade < self.cooldown_seconds:
                return
            
            # MCX is Overpriced -> Sell MCX
            if divergence_pct > self.params['divergence_threshold']:
                self.logger.info(f"SIGNAL: SELL {self.symbol} at {current['mcx_price']:.2f} | Reason: MCX Premium > {self.params['divergence_threshold']}%")
                if self.execute_trade("SELL", self.quantity, current['mcx_price']):
                    self.last_trade_time = time.time()

            # MCX is Underpriced -> Buy MCX
            elif divergence_pct < -self.params['divergence_threshold']:
                self.logger.info(f"SIGNAL: BUY {self.symbol} at {current['mcx_price']:.2f} | Reason: MCX Discount > {self.params['divergence_threshold']}%")
                if self.execute_trade("BUY", self.quantity, current['mcx_price']):
                    self.last_trade_time = time.time()

        # Exit Logic
        elif current_pos != 0:
            abs_div = abs(divergence_pct)
            if abs_div < self.params['convergence_threshold']:
                side = "BUY" if current_pos < 0 else "SELL"
                self.logger.info(f"SIGNAL: {side} {self.symbol} at {current['mcx_price']:.2f} | Reason: Convergence reached")
                if self.execute_trade(side, abs(current_pos), current['mcx_price']):
                    self.last_trade_time = time.time()

if __name__ == "__main__":
    MCXGlobalArbitrageStrategy.cli()
