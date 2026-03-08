#!/usr/bin/env python3
"""
MCX Global Arbitrage Strategy
Trades MCX Commodities by tracking divergence from global benchmarks (e.g., COMEX Gold via yfinance).
"""
import time
import argparse
import pandas as pd
from datetime import datetime

# Simplified Import using strategy_preamble
from strategy_preamble import BaseStrategy

try:
    import yfinance as yf
except ImportError:
    yf = None

class MCXGlobalArbitrageStrategy(BaseStrategy):
    def setup(self):
        # Additional custom setup for this strategy
        self.global_symbol = getattr(self, "global_symbol", "GC=F")
        self.params = {
            'divergence_threshold': 0.15,
            'convergence_threshold': 0.05,
            'cooldown_seconds': 3600
        }
        self.data = pd.DataFrame()
        self.session_ref_mcx = None
        self.session_ref_global = None
        self.position = 0
        self.last_trade_time = 0

        self.logger.info(f"Initialized MCX Global Arbitrage Strategy: {self.symbol} vs {self.global_symbol}")
        if not yf:
            self.logger.warning("yfinance not installed. Global prices will fail to fetch unless using local API fallback.")

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--global_symbol', type=str, default='GC=F', help='Global Symbol for comparison (e.g. GC=F)')

    def fetch_data(self):
        """Fetch live MCX and Global prices. Returns True on success."""
        if not self.client:
            self.logger.error("❌ CRITICAL: No API client available. Strategy requires API client.")
            return False
        
        try:
            # 1. Fetch MCX Price
            mcx_quote = self.client.get_quote(self.symbol, exchange="MCX")
            
            if not mcx_quote or 'ltp' not in mcx_quote:
                self.logger.warning(f"Failed to fetch MCX price for {self.symbol}. Retrying...")
                return False
            
            mcx_price = float(mcx_quote['ltp'])

            # 2. Fetch Global Price
            global_price = None
            
            # Fallback to yfinance for global prices
            if global_price is None and yf:
                try:
                    ticker = yf.Ticker(self.global_symbol)
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
        
        if self.position == 0:
            if time_since_last_trade < self.params['cooldown_seconds']:
                return
            
            # MCX is Overpriced -> Sell MCX
            if divergence_pct > self.params['divergence_threshold']:
                self.entry("SELL", current['mcx_price'], f"MCX Premium > {self.params['divergence_threshold']}% (Rel to Global)")

            # MCX is Underpriced -> Buy MCX
            elif divergence_pct < -self.params['divergence_threshold']:
                self.entry("BUY", current['mcx_price'], f"MCX Discount > {self.params['divergence_threshold']}% (Rel to Global)")

        # Exit Logic
        elif self.position != 0:
            abs_div = abs(divergence_pct)
            if abs_div < self.params['convergence_threshold']:
                side = "BUY" if self.position == -1 else "SELL"
                self.exit(side, current['mcx_price'], "Convergence reached")

    def entry(self, side, price, reason):
        self.logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Reason: {reason}")
        qty = self.get_adaptive_quantity(price, risk_pct=1.0, capital=500000)

        if self.client:
            try:
                self.client.placesmartorder(
                    strategy="MCX Global Arbitrage",
                    symbol=self.symbol,
                    action=side,
                    exchange="MCX",
                    price_type="MARKET",
                    product="MIS",
                    quantity=qty,
                    position_size=qty
                )
                self.logger.info(f"[ENTRY] Order placed: {side} {self.symbol} @ {price:.2f} Qty: {qty}")
                self.position = qty if side == "BUY" else -qty
                self.last_trade_time = time.time()
            except Exception as e:
                self.logger.error(f"[ENTRY] Order placement failed: {e}")
        else:
            self.logger.warning(f"[ENTRY] No API client available - signal logged but order not placed")

    def exit(self, side, price, reason):
        self.logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Reason: {reason}")
        
        if self.client:
            try:
                self.client.placesmartorder(
                    strategy="MCX Global Arbitrage",
                    symbol=self.symbol,
                    action=side,
                    exchange="MCX",
                    price_type="MARKET",
                    product="MIS",
                    quantity=abs(self.position),
                    position_size=0
                )
                self.logger.info(f"[EXIT] Order placed: {side} {self.symbol} @ {price:.2f}")
                self.position = 0
                self.last_trade_time = time.time()
            except Exception as e:
                self.logger.error(f"[EXIT] Order placement failed: {e}")
        else:
            self.logger.warning(f"[EXIT] No API client available - signal logged but order not placed")

    def run(self):
        self.logger.info(f"Starting MCX Global Arbitrage Strategy loop for {self.symbol}")
        while True:
            if self.fetch_data():
                self.check_signals()
            time.sleep(60)

if __name__ == "__main__":
    MCXGlobalArbitrageStrategy.cli()
