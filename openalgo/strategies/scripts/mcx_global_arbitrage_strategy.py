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

# Add utils directory to path for imports
utils_path = Path(__file__).parent.parent / 'utils'
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))

try:
    from trading_utils import APIClient
    from symbol_resolver import SymbolResolver
except ImportError:
    try:
        from openalgo.strategies.utils.trading_utils import APIClient
        from openalgo.strategies.utils.symbol_resolver import SymbolResolver
    except ImportError:
        APIClient = None
        SymbolResolver = None

# Configuration
SYMBOL = os.getenv('SYMBOL', None)
GLOBAL_SYMBOL = os.getenv('GLOBAL_SYMBOL', 'GC=F') # Default to Gold Futures
API_HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')

# Strategy Parameters
PARAMS = {
    'divergence_threshold': 3.0, # Percent
    'convergence_threshold': 1.5, # Percent
    'lookback_period': 20,
}

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(f"MCX_Arbitrage_{SYMBOL}")

class MCXGlobalArbitrageStrategy:
    def __init__(self, symbol, global_symbol, params, api_client=None):
        self.symbol = symbol
        self.global_symbol = global_symbol
        self.params = params
        self.position = 0
        self.data = pd.DataFrame()
        self.api_client = api_client
        self.last_trade_time = 0
        self.cooldown_seconds = 300

        # Session Reference Points (Opening Price of the session/day)
        self.session_ref_mcx = None
        self.session_ref_global = None

    def fetch_data(self):
        """Fetch live MCX and Global prices. Returns True on success."""
        if not self.api_client:
            logger.error("❌ CRITICAL: No API client available. Strategy requires API client.")
            return False
        
        try:
            logger.info(f"Fetching data for {self.symbol} vs {self.global_symbol}...")

            # 1. Fetch MCX Price from Kite API
            mcx_quote = self.api_client.get_quote(self.symbol, exchange="MCX")
            
            if not mcx_quote or 'ltp' not in mcx_quote:
                logger.warning(f"Failed to fetch MCX price for {self.symbol}. Retrying...")
                return False
            
            mcx_price = float(mcx_quote['ltp'])

            # 2. Fetch Global Price
            global_price = None
            
            # Try fetching from Kite if it looks like a Kite symbol (no '=')
            if '=' not in self.global_symbol:
                try:
                    global_quote = self.api_client.get_quote(self.global_symbol, exchange="MCX") # Or other exchange
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
                    logger.warning(f"Failed to fetch global price from yfinance: {e}")

            if global_price is None:
                logger.warning(f"Could not fetch global price for {self.global_symbol}")
                return False

            current_time = datetime.now()

            # Initialize Session Reference if None (First run of the day)
            if self.session_ref_mcx is None:
                self.session_ref_mcx = mcx_price
                self.session_ref_global = global_price
                logger.info(f"Session Start Reference: MCX={mcx_price}, Global={global_price}")

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
            logger.error(f"Error fetching data: {e}", exc_info=True)
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

        logger.info(f"MCX Chg: {mcx_change_pct:.2f}% | Global Chg: {global_change_pct:.2f}% | Divergence: {divergence_pct:.2f}%")
        
        # Entry Logic
        current_time = time.time()
        time_since_last_trade = current_time - self.last_trade_time
        
        if self.position == 0:
            if time_since_last_trade < self.cooldown_seconds:
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
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Reason: {reason}")
        
        order_placed = False
        if self.api_client:
            try:
                response = self.api_client.placesmartorder(
                    strategy="MCX Global Arbitrage",
                    symbol=self.symbol,
                    action=side,
                    exchange="MCX",
                    price_type="MARKET",
                    product="MIS",
                    quantity=1,
                    position_size=1
                )
                logger.info(f"[ENTRY] Order placed: {side} {self.symbol} @ {price:.2f}")
                order_placed = True
            except Exception as e:
                logger.error(f"[ENTRY] Order placement failed: {e}")
        else:
            logger.warning(f"[ENTRY] No API client available - signal logged but order not placed")
        
        if order_placed or not self.api_client: # Assume success if no client (testing)
            self.position = 1 if side == "BUY" else -1
            self.last_trade_time = time.time()

    def exit(self, side, price, reason):
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Reason: {reason}")
        
        order_placed = False
        if self.api_client:
            try:
                response = self.api_client.placesmartorder(
                    strategy="MCX Global Arbitrage",
                    symbol=self.symbol,
                    action=side,
                    exchange="MCX",
                    price_type="MARKET",
                    product="MIS",
                    quantity=abs(self.position),
                    position_size=0
                )
                logger.info(f"[EXIT] Order placed: {side} {self.symbol} @ {price:.2f}")
                order_placed = True
            except Exception as e:
                logger.error(f"[EXIT] Order placement failed: {e}")
        else:
            logger.warning(f"[EXIT] No API client available - signal logged but order not placed")
        
        if order_placed or not self.api_client:
            self.position = 0
            self.last_trade_time = time.time()

    def run(self):
        logger.info(f"Starting MCX Global Arbitrage Strategy for {self.symbol} vs {self.global_symbol}")
        
        while True:
            if self.fetch_data():
                self.check_signals()
            time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MCX Global Arbitrage Strategy')
    parser.add_argument('--symbol', type=str, help='MCX Symbol (e.g., GOLDM05FEB26FUT)')
    parser.add_argument('--global_symbol', type=str, default='GC=F', help='Global Symbol for comparison (e.g. GC=F)')
    parser.add_argument('--port', type=int, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    args = parser.parse_args()

    # Use command-line args or env vars
    if args.symbol: SYMBOL = args.symbol
    elif os.getenv('SYMBOL'): SYMBOL = os.getenv('SYMBOL')
    
    if args.global_symbol: GLOBAL_SYMBOL = args.global_symbol
    elif os.getenv('GLOBAL_SYMBOL'): GLOBAL_SYMBOL = os.getenv('GLOBAL_SYMBOL')
    
    if args.port: API_HOST = f"http://127.0.0.1:{args.port}"
    elif os.getenv('OPENALGO_PORT'): API_HOST = f"http://127.0.0.1:{os.getenv('OPENALGO_PORT')}"
    
    if args.api_key: API_KEY = args.api_key
    else: API_KEY = os.getenv('OPENALGO_APIKEY', API_KEY)

    # Validate symbol or resolve default
    if not SYMBOL:
        if SymbolResolver:
            logger.info("Resolving default MCX Gold symbol...")
            resolver = SymbolResolver()
            SYMBOL = resolver.resolve({'underlying': 'GOLD', 'type': 'FUT', 'exchange': 'MCX'})
            if not SYMBOL:
                 SYMBOL = "GOLDM05FEB26FUT"
                 logger.warning(f"Could not resolve symbol, using fallback: {SYMBOL}")
            else:
                 logger.info(f"Resolved to: {SYMBOL}")
        else:
             SYMBOL = "GOLDM05FEB26FUT"
             logger.warning("SymbolResolver not available, using hardcoded fallback.")

    # Initialize API client
    api_client = None
    if APIClient:
        try:
            api_client = APIClient(api_key=API_KEY, host=API_HOST)
            logger.info(f"API client initialized for {API_HOST}")
        except Exception as e:
            logger.warning(f"Could not create APIClient: {e}. Strategy will run in signal-only mode.")
    else:
        logger.warning("APIClient not available. Strategy will run in signal-only mode.")

    strategy = MCXGlobalArbitrageStrategy(SYMBOL, GLOBAL_SYMBOL, PARAMS, api_client=api_client)
    strategy.run()
