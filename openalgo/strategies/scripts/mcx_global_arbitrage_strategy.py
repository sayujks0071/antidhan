#!/usr/bin/env python3
"""
MCX Global Arbitrage Strategy
"""
import os
import sys
import logging
import time
from datetime import datetime
import pandas as pd
import numpy as np

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
    def __init__(self, symbol, quantity, api_key=None, host=None, ignore_time=False,
                 log_file=None, client=None, **kwargs):
        super().__init__(
            name="MCX_Global_Arbitrage",
            symbol=symbol,
            quantity=quantity,
            interval="1m", # Run every minute
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
            'global_symbol': kwargs.get('global_symbol', 'GC=F')
        }
        self.params.update(kwargs)

        self.global_symbol = self.params['global_symbol']
        self.cooldown_seconds = 300
        self.last_trade_time = 0

        # Session Reference Points
        self.session_ref_mcx = None
        self.session_ref_global = None
        self.last_session_date = None
        
        self.data_history = pd.DataFrame() # Local history for debug/logs

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--global_symbol", type=str, default="GC=F", help="Global Symbol for comparison (e.g. GC=F)")
        parser.add_argument("--port", type=int, help="API Port")
        parser.add_argument("--divergence_threshold", type=float, default=3.0, help="Divergence Threshold %")
        parser.add_argument("--convergence_threshold", type=float, default=1.5, help="Convergence Threshold %")

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        if args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"

        kwargs['global_symbol'] = args.global_symbol
        kwargs['divergence_threshold'] = args.divergence_threshold
        kwargs['convergence_threshold'] = args.convergence_threshold
        return kwargs

    def cycle(self):
        # Reset Session Reference if new day
        today = datetime.now().date()
        if self.last_session_date != today:
            self.session_ref_mcx = None
            self.session_ref_global = None
            self.last_session_date = today
            self.logger.info("New session started. Resetting reference points.")

        # Fetch Data
        mcx_price = self.get_mcx_price()
        global_price = self.get_global_price()

        if mcx_price is None or global_price is None:
            return

        # Initialize Reference
        if self.session_ref_mcx is None:
            self.session_ref_mcx = mcx_price
            self.session_ref_global = global_price
            self.logger.info(f"Session Start Reference: MCX={mcx_price}, Global={global_price}")
            return

        # Calculate Percentage Change
        mcx_change_pct = ((mcx_price - self.session_ref_mcx) / self.session_ref_mcx) * 100
        global_change_pct = ((global_price - self.session_ref_global) / self.session_ref_global) * 100

        # Divergence
        divergence_pct = mcx_change_pct - global_change_pct
        
        self.logger.info(f"MCX: {mcx_price} ({mcx_change_pct:.2f}%) | Global: {global_price} ({global_change_pct:.2f}%) | Div: {divergence_pct:.2f}%")

        # Trading Logic
        current_time = time.time()
        time_since_last_trade = current_time - self.last_trade_time
        
        has_position = self.pm.has_position() if self.pm else False
        pos_qty = self.pm.position if self.pm else 0

        if not has_position:
            if time_since_last_trade < self.cooldown_seconds:
                return
            
            # MCX Overpriced -> Sell
            if divergence_pct > self.params['divergence_threshold']:
                self.logger.info(f"Signal: SELL MCX (Premium > {self.params['divergence_threshold']}%)")
                if self.execute_trade('SELL', self.quantity, mcx_price):
                    self.last_trade_time = current_time

            # MCX Underpriced -> Buy
            elif divergence_pct < -self.params['divergence_threshold']:
                self.logger.info(f"Signal: BUY MCX (Discount > {self.params['divergence_threshold']}%)")
                if self.execute_trade('BUY', self.quantity, mcx_price):
                    self.last_trade_time = current_time

        elif has_position:
            # Exit Logic (Convergence)
            abs_div = abs(divergence_pct)
            if abs_div < self.params['convergence_threshold']:
                side = "BUY" if pos_qty < 0 else "SELL"
                self.logger.info(f"Signal: EXIT (Convergence reached)")
                if self.execute_trade(side, abs(pos_qty), mcx_price):
                    self.last_trade_time = current_time

    def get_mcx_price(self):
        # Use BaseStrategy client
        if not self.client: return None
        quote = self.client.get_quote(self.symbol, exchange=self.exchange)
        if quote and 'ltp' in quote:
            return float(quote['ltp'])
        return None

    def get_global_price(self):
        # Try fetching from API first (if it's a traded symbol)
        if '=' not in self.global_symbol:
            # Default to MCX for global symbols traded on local exchange
            quote = self.client.get_quote(self.global_symbol, exchange="MCX")
            if quote and 'ltp' in quote:
                return float(quote['ltp'])
        
        # Fallback to yfinance
        if yf:
            try:
                ticker = yf.Ticker(self.global_symbol)
                hist = ticker.history(period="1d")
                if not hist.empty:
                    return hist['Close'].iloc[-1]
            except Exception as e:
                self.logger.warning(f"YFinance error: {e}")
        
        return None

if __name__ == "__main__":
    MCXGlobalArbitrageStrategy.cli()
