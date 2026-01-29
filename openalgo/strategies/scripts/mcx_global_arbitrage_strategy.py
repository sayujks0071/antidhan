import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import json
import httpx
from pathlib import Path

# Add utils directory to path for imports
utils_path = Path(__file__).parent.parent / 'utils'
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))

try:
    from trading_utils import APIClient
except ImportError:
    try:
        from openalgo.strategies.utils.trading_utils import APIClient
    except ImportError:
        APIClient = None

# Configuration
SYMBOL = os.getenv('SYMBOL', 'GOLDM05FEB26FUT')  # Default to Gold futures
GLOBAL_SYMBOL = os.getenv('GLOBAL_SYMBOL', 'GOLD_GLOBAL')  # Default global symbol
API_HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')

# Strategy Parameters
PARAMS = {
    'divergence_threshold': 3.0, # Percent
    'convergence_threshold': 1.5, # Percent (increased from 0.5% to prevent premature exits)
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
        self.last_trade_time = 0  # Track last trade time for cooldown
        self.cooldown_seconds = 300  # 5 minutes cooldown between trades
        # #region agent log
        debug_log_path = "/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log"
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:35","message":"Strategy __init__","data":{"symbol":symbol,"has_api_client":api_client is not None},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion

    def fetch_data(self):
        """Fetch live MCX and Global prices from Kite API via OpenAlgo."""
        # #region agent log
        debug_log_path = "/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log"
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:60","message":"fetch_data() entry","data":{"using_real_api":True,"has_api_client":self.api_client is not None},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion
        
        if not self.api_client:
            logger.error("❌ CRITICAL: No API client available. Cannot fetch real data. Strategy stopping.")
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:66","message":"No API client - stopping strategy","data":{"will_stop":True},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
            raise RuntimeError("Cannot trade without real API data. Strategy requires API client.")
        
        try:
            logger.info(f"Fetching REAL data for {self.symbol} vs {self.global_symbol}...")

            # Fetch REAL MCX Price from Kite API
            mcx_quote = self.api_client.get_quote(self.symbol, exchange="MCX")
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:75","message":"MCX quote fetched","data":{"quote_success":mcx_quote is not None,"has_ltp":mcx_quote.get('ltp') is not None if mcx_quote else False},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
            
            if not mcx_quote or 'ltp' not in mcx_quote:
                logger.error(f"❌ CRITICAL: Failed to fetch REAL MCX price for {self.symbol} from Kite API.")
                logger.error("❌ Strategy STOPPING - Cannot trade without real market data.")
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:81","message":"MCX quote fetch failed - stopping strategy","data":{"will_stop":True},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
                raise RuntimeError(f"Cannot fetch real MCX price for {self.symbol}. Strategy requires real Kite API data.")
            
            mcx_price = float(mcx_quote['ltp'])

            # For global price, we need to fetch from a global gold API or use a conversion
            # Since we don't have direct access to global gold prices, we'll use MCX price as reference
            # and note that this strategy requires a real global price source
            # For now, if global_symbol is not available via API, we'll skip trading
            global_quote = self.api_client.get_quote(self.global_symbol, exchange="MCX")
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:95","message":"Global quote fetch attempt","data":{"quote_success":global_quote is not None,"has_ltp":global_quote.get('ltp') is not None if global_quote else False},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
            
            if not global_quote or 'ltp' not in global_quote:
                logger.error(f"❌ CRITICAL: Cannot fetch REAL global price for {self.global_symbol} from Kite API.")
                logger.error("❌ Strategy STOPPING - Cannot trade without real global price data.")
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:101","message":"Global quote fetch failed - stopping strategy","data":{"will_stop":True},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
                raise RuntimeError(f"Cannot fetch real global price for {self.global_symbol}. Strategy requires real Kite API data.")
            
            global_price = float(global_quote['ltp'])
            
            # #region agent log
            try:
                divergence_pct = ((mcx_price - global_price) / global_price) * 100
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:109","message":"Real prices fetched successfully","data":{"mcx_price":float(mcx_price),"global_price":float(global_price),"divergence_pct":float(divergence_pct),"using_real_data":True},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion

            current_time = datetime.now()

            new_row = pd.DataFrame({
                'timestamp': [current_time],
                'mcx_price': [mcx_price],
                'global_price': [global_price]
            })

            self.data = pd.concat([self.data, new_row], ignore_index=True)
            if len(self.data) > 100:
                self.data = self.data.iloc[-100:]

        except RuntimeError:
            # Re-raise RuntimeError (no API client)
            raise
        except Exception as e:
            logger.error(f"Error fetching real data: {e}", exc_info=True)
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:127","message":"Exception in fetch_data","data":{"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion

    def check_signals(self):
        """Check for arbitrage opportunities."""
        # #region agent log
        debug_log_path = "/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log"
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:92","message":"check_signals() entry","data":{"data_empty":self.data.empty,"position":self.position,"divergence_threshold":self.params['divergence_threshold'],"convergence_threshold":self.params['convergence_threshold']},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion
        if self.data.empty:
            return

        current = self.data.iloc[-1]

        # Calculate Divergence %
        diff = current['mcx_price'] - current['global_price']
        divergence_pct = (diff / current['global_price']) * 100

        logger.info(f"Divergence: {divergence_pct:.2f}% (MCX: {current['mcx_price']:.2f}, Global: {current['global_price']:.2f})")
        
        # #region agent log
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:103","message":"Divergence calculated","data":{"divergence_pct":divergence_pct,"mcx_price":current['mcx_price'],"global_price":current['global_price'],"abs_divergence":abs(divergence_pct)},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion

        # Entry Logic
        current_time = time.time()
        time_since_last_trade = current_time - self.last_trade_time
        # #region agent log
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"mcx_global_arbitrage_strategy.py:108","message":"Checking cooldown","data":{"position":self.position,"time_since_last_trade":time_since_last_trade,"cooldown_seconds":self.cooldown_seconds,"cooldown_active":time_since_last_trade < self.cooldown_seconds},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion
        
        if self.position == 0:
            # Check cooldown period
            if time_since_last_trade < self.cooldown_seconds:
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"mcx_global_arbitrage_strategy.py:115","message":"Cooldown active - skipping entry","data":{"time_since_last_trade":time_since_last_trade,"cooldown_remaining":self.cooldown_seconds - time_since_last_trade},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
                logger.debug(f"Cooldown active. {self.cooldown_seconds - int(time_since_last_trade)}s remaining before next trade.")
                return
            
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"mcx_global_arbitrage_strategy.py:122","message":"Checking entry conditions","data":{"position":self.position,"divergence_pct":divergence_pct,"divergence_threshold":self.params['divergence_threshold'],"will_enter_sell":divergence_pct > self.params['divergence_threshold'],"will_enter_buy":divergence_pct < -self.params['divergence_threshold']},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
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
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"mcx_global_arbitrage_strategy.py:120","message":"Checking exit conditions","data":{"position":self.position,"abs_divergence":abs_div,"convergence_threshold":self.params['convergence_threshold'],"will_exit":abs_div < self.params['convergence_threshold']},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
            if abs_div < self.params['convergence_threshold']:
                side = "BUY" if self.position == -1 else "SELL"
                self.exit(side, current['mcx_price'], "Convergence reached")

    def entry(self, side, price, reason):
        # #region agent log
        debug_log_path = "/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log"
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"mcx_global_arbitrage_strategy.py:98","message":"entry() called","data":{"side":side,"price":price,"reason":reason,"has_api_client":self.api_client is not None,"position_before":self.position},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Reason: {reason}")
        
        # Place order if API client is available
        order_placed = False
        order_error = None
        if self.api_client:
            try:
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"mcx_global_arbitrage_strategy.py:105","message":"Attempting order placement","data":{"side":side,"symbol":self.symbol,"quantity":1,"exchange":"MCX","product":"MIS"},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
                response = self.api_client.placesmartorder(
                    strategy="MCX Global Arbitrage",
                    symbol=self.symbol,
                    action=side,
                    exchange="MCX",
                    price_type="MARKET",
                    product="MIS",
                    quantity=1,  # Default quantity for MCX
                    position_size=1
                )
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"mcx_global_arbitrage_strategy.py:115","message":"Order placement response","data":{"response":str(response)[:200],"order_placed":True},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
                logger.info(f"[ENTRY] Order placed: {side} {self.symbol} @ {price:.2f} | Order ID: {response.get('orderid', 'N/A') if isinstance(response, dict) else 'N/A'}")
                order_placed = True
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"mcx_global_arbitrage_strategy.py:160","message":"Order placement successful","data":{"response_status":response.get('status') if isinstance(response, dict) else None,"orderid":response.get('orderid') if isinstance(response, dict) else None,"order_placed":True},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
            except Exception as e:
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"mcx_global_arbitrage_strategy.py:120","message":"Order placement failed","data":{"error":str(e),"order_placed":False},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
                logger.error(f"[ENTRY] Order placement failed: {e}")
                order_error = str(e)
        else:
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:125","message":"No API client available","data":{"order_placed":False,"reason":"no_api_client"},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
            logger.warning(f"[ENTRY] No API client available - signal logged but order not placed")
        
        # #region agent log
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"mcx_global_arbitrage_strategy.py:130","message":"Before position update","data":{"will_update_position":True,"order_placed":order_placed},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion
        # Only update position if order was actually placed successfully
        if order_placed:
            self.position = 1 if side == "BUY" else -1
            self.last_trade_time = time.time()  # Update last trade time
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"mcx_global_arbitrage_strategy.py:186","message":"Position updated after successful order","data":{"position_after":self.position,"order_placed":order_placed,"last_trade_time":self.last_trade_time},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
        else:
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"mcx_global_arbitrage_strategy.py:192","message":"Position NOT updated - order failed","data":{"position_unchanged":self.position,"order_placed":order_placed,"order_error":order_error},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion

    def exit(self, side, price, reason):
        # #region agent log
        debug_log_path = "/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log"
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"mcx_global_arbitrage_strategy.py:102","message":"exit() called","data":{"side":side,"price":price,"reason":reason,"has_api_client":self.api_client is not None,"position_before":self.position},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Reason: {reason}")
        
        # Place exit order if API client is available
        order_placed = False
        order_error = None
        if self.api_client:
            try:
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"mcx_global_arbitrage_strategy.py:145","message":"Attempting exit order placement","data":{"side":side,"symbol":self.symbol,"quantity":abs(self.position),"exchange":"MCX","product":"MIS"},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
                response = self.api_client.placesmartorder(
                    strategy="MCX Global Arbitrage",
                    symbol=self.symbol,
                    action=side,
                    exchange="MCX",
                    price_type="MARKET",
                    product="MIS",
                    quantity=abs(self.position),
                    position_size=0  # Closing position
                )
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"mcx_global_arbitrage_strategy.py:155","message":"Exit order placement response","data":{"response":str(response)[:200],"order_placed":True},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
                logger.info(f"[EXIT] Order placed: {side} {self.symbol} @ {price:.2f} | Order ID: {response.get('orderid', 'N/A') if isinstance(response, dict) else 'N/A'}")
                order_placed = True
            except Exception as e:
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"mcx_global_arbitrage_strategy.py:160","message":"Exit order placement failed","data":{"error":str(e),"order_placed":False},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
                logger.error(f"[EXIT] Order placement failed: {e}")
                order_error = str(e)
        else:
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:165","message":"No API client for exit","data":{"order_placed":False,"reason":"no_api_client"},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
            logger.warning(f"[EXIT] No API client available - signal logged but order not placed")
        
        # #region agent log
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"mcx_global_arbitrage_strategy.py:170","message":"Before position reset","data":{"will_reset_position":True,"order_placed":order_placed},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion
        # Only reset position if order was actually placed successfully
        if order_placed:
            self.position = 0
            self.last_trade_time = time.time()  # Update last trade time
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"mcx_global_arbitrage_strategy.py:257","message":"Position reset after successful exit order","data":{"position_after":self.position,"order_placed":order_placed,"last_trade_time":self.last_trade_time},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
        else:
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"mcx_global_arbitrage_strategy.py:263","message":"Position NOT reset - exit order failed","data":{"position_unchanged":self.position,"order_placed":order_placed,"order_error":order_error},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion

    def run(self):
        logger.info(f"Starting MCX Global Arbitrage Strategy for {self.symbol}")
        logger.info("⚠️  IMPORTANT: Strategy uses REAL Kite API data only. No mocked data.")
        consecutive_failures = 0
        max_consecutive_failures = 5
        
        while True:
            try:
                self.fetch_data()
                self.check_signals()
                consecutive_failures = 0  # Reset on success
            except RuntimeError as e:
                # No API client - stop strategy
                logger.error(f"❌ CRITICAL ERROR: {e}")
                logger.error("Strategy stopping. Cannot trade without real API data.")
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Error in strategy loop: {e}")
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"❌ Too many consecutive failures ({consecutive_failures}). Stopping strategy.")
                    break
            
            time.sleep(60) # Check every minute for arbitrage

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MCX Global Arbitrage Strategy')
    parser.add_argument('--symbol', type=str, help='MCX Symbol (e.g., GOLDM05FEB26FUT)')
    parser.add_argument('--global_symbol', type=str, help='Global Symbol for comparison')
    parser.add_argument('--port', type=int, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    args = parser.parse_args()

    # Use command-line args if provided, otherwise fall back to environment variables
    # OpenAlgo sets environment variables, so this allows both methods
    if args.symbol:
        SYMBOL = args.symbol
    elif os.getenv('SYMBOL'):
        SYMBOL = os.getenv('SYMBOL')
    
    if args.global_symbol:
        GLOBAL_SYMBOL = args.global_symbol
    elif os.getenv('GLOBAL_SYMBOL'):
        GLOBAL_SYMBOL = os.getenv('GLOBAL_SYMBOL')
    
    if args.port:
        API_HOST = f"http://127.0.0.1:{args.port}"
    elif os.getenv('OPENALGO_PORT'):
        API_HOST = f"http://127.0.0.1:{os.getenv('OPENALGO_PORT')}"
    
    if args.api_key:
        API_KEY = args.api_key
    else:
        # Use environment variable (set by OpenAlgo)
        API_KEY = os.getenv('OPENALGO_APIKEY', API_KEY)

    # Validate symbol is not REPLACE_ME
    if SYMBOL == "REPLACE_ME" or GLOBAL_SYMBOL == "REPLACE_ME_GLOBAL":
        logger.error(f"❌ Symbol not configured! SYMBOL={SYMBOL}, GLOBAL_SYMBOL={GLOBAL_SYMBOL}")
        logger.error("Please set SYMBOL environment variable or use --symbol argument")
        logger.error("Example: --symbol GOLDM05FEB26FUT --global_symbol GOLD_GLOBAL")
        exit(1)

    # Initialize API client
    debug_log_path = "/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log"
    api_client = None
    if APIClient:
        try:
            api_client = APIClient(api_key=API_KEY, host=API_HOST)
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:151","message":"API client initialized","data":{"api_key_set":bool(API_KEY),"host":API_HOST,"client_created":True},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
            logger.info(f"API client initialized for {API_HOST}")
        except Exception as e:
            logger.warning(f"Could not create APIClient: {e}. Strategy will run in signal-only mode.")
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:157","message":"API client creation failed","data":{"error":str(e),"client_created":False},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
    else:
        logger.warning("APIClient not available. Strategy will run in signal-only mode.")
        # #region agent log
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"mcx_global_arbitrage_strategy.py:163","message":"APIClient class not found","data":{"client_created":False,"reason":"import_failed"},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion

    strategy = MCXGlobalArbitrageStrategy(SYMBOL, GLOBAL_SYMBOL, PARAMS, api_client=api_client)
    strategy.run()
