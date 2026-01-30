import os
import time
import logging
import pytz
import json
import time as time_module
from pathlib import Path
from datetime import datetime, time as dt_time
import httpx
import pandas as pd
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TradingUtils")

def is_market_open():
    """
    Check if NSE market is open (09:15 - 15:30 IST) on weekdays.
    """
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)

    # Check weekend
    if now.weekday() >= 5: # 5=Sat, 6=Sun
        return False

    market_start = dt_time(9, 15)
    market_end = dt_time(15, 30)
    current_time = now.time()

    return market_start <= current_time <= market_end

def calculate_intraday_vwap(df):
    """
    Calculate VWAP resetting daily.
    Expects DataFrame with 'datetime' (or index), 'close', 'high', 'low', 'volume'.
    """
    df = df.copy()
    
    # Handle datetime column or index
    if isinstance(df.index, pd.DatetimeIndex):
        df['datetime'] = df.index
    elif 'datetime' not in df.columns and 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    elif 'datetime' not in df.columns:
        # If no datetime info, create from index if it's numeric (Unix timestamp)
        if df.index.dtype in ['int64', 'float64']:
            df['datetime'] = pd.to_datetime(df.index, unit='s')
        else:
            df['datetime'] = pd.to_datetime(df.index)

    # Ensure datetime is datetime object
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['date'] = df['datetime'].dt.date

    # Typical Price
    df['tp'] = (df['high'] + df['low'] + df['close']) / 3
    df['pv'] = df['tp'] * df['volume']

    # Group by Date and calculate cumulative sums
    df['cum_pv'] = df.groupby('date')['pv'].cumsum()
    df['cum_vol'] = df.groupby('date')['volume'].cumsum()

    df['vwap'] = df['cum_pv'] / df['cum_vol']

    # Deviation
    df['vwap_dev'] = (df['close'] - df['vwap']) / df['vwap']

    return df

class PositionManager:
    """
    Persistent position manager to track trades and prevent duplicate orders.
    Saves state to openalgo/strategies/state/{symbol}_state.json
    """
    def __init__(self, symbol):
        self.symbol = symbol
        # Determine state directory relative to this file
        # this file: openalgo/strategies/utils/trading_utils.py
        # target: openalgo/strategies/state/
        self.state_dir = Path(__file__).resolve().parent.parent / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / f"{self.symbol}_state.json"

        self.position = 0
        self.entry_price = 0.0
        self.pnl = 0.0

        self.load_state()

    def load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.position = data.get('position', 0)
                    self.entry_price = data.get('entry_price', 0.0)
                    self.pnl = data.get('pnl', 0.0)
                    logger.info(f"Loaded state for {self.symbol}: Pos={self.position} @ {self.entry_price}")
            except Exception as e:
                logger.error(f"Failed to load state for {self.symbol}: {e}")

    def save_state(self):
        try:
            data = {
                'position': self.position,
                'entry_price': self.entry_price,
                'pnl': self.pnl,
                'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save state for {self.symbol}: {e}")

    def update_position(self, qty, price, side):
        """
        Update position state.
        side: 'BUY' or 'SELL'
        """
        side = side.upper()

        if side == 'BUY':
            if self.position == 0:
                self.entry_price = price # Long Entry
            elif self.position < 0:
                # Closing Short
                realized_pnl = (self.entry_price - price) * qty
                self.pnl += realized_pnl
                logger.info(f"Closed Short. PnL: {realized_pnl}")

            self.position += qty

        elif side == 'SELL':
            if self.position == 0:
                self.entry_price = price # Short Entry
            elif self.position > 0:
                # Closing Long
                realized_pnl = (price - self.entry_price) * qty
                self.pnl += realized_pnl
                logger.info(f"Closed Long. PnL: {realized_pnl}")

            self.position -= qty

        if self.position == 0:
            self.entry_price = 0.0

        logger.info(f"Position Updated for {self.symbol}: {self.position} @ {self.entry_price}")
        self.save_state()

    def has_position(self):
        return self.position != 0

class SmartOrder:
    """
    Intelligent Order Execution logic.
    Wraps an API client to provide advanced order capabilities.
    """
    def __init__(self, api_client):
        self.client = api_client

    def place_adaptive_order(self, strategy, symbol, action, exchange, quantity,
                           limit_price=None, product='MIS',
                           urgency='MEDIUM'):
        """
        Place an order adapting to market conditions.

        Args:
            urgency: 'LOW' (Passive Limit), 'MEDIUM' (Limit then Market), 'HIGH' (Market)
        """
        logger.info(f"SmartOrder: Placing {action} {quantity} {symbol} (Urgency: {urgency})")

        order_type = "LIMIT" if limit_price else "MARKET"
        price = limit_price if limit_price else 0

        # Override based on urgency
        if urgency == 'HIGH':
            order_type = "MARKET"
            price = 0
        elif urgency == 'LOW' and not limit_price:
            # Low urgency but no limit price provided? Fallback to Market but warn
            logger.warning("SmartOrder: Low urgency requested but no limit price. Using MARKET.")
            order_type = "MARKET"

        # In a real async system, we would:
        # 1. Place Limit at Bid/Ask
        # 2. Wait 5s
        # 3. Check fill
        # 4. Cancel & Replace if not filled

        # Since this is a synchronous/blocking call in this architecture:
        # We rely on the 'smartorder' endpoint of the broker/server if available,
        # or just place the simple order.

        # However, we can simulate "Smartness" by choosing the right parameters

        try:
            # Use the client's place_smart_order if available (wrapper around placesmartorder)
            # Or use standard place_order
            if hasattr(self.client, 'placesmartorder'):
                return self.client.placesmartorder(
                    strategy=strategy,
                    symbol=symbol,
                    action=action,
                    exchange=exchange,
                    price_type=order_type,
                    product=product,
                    quantity=quantity,
                    position_size=quantity # Simplification
                )
            else:
                logger.error("SmartOrder: Client does not support 'placesmartorder'")
                return None

        except Exception as e:
            logger.error(f"SmartOrder Failed: {e}")
            return None

    def get_pnl(self, current_price):
        if self.position == 0:
            return 0.0

        if self.position > 0:
            return (current_price - self.entry_price) * abs(self.position)
        else:
            return (self.entry_price - current_price) * abs(self.position)

class APIClient:
    """
    Fallback API Client using httpx if openalgo package is missing.
    """
    def __init__(self, api_key, host="http://127.0.0.1:5001"):
        self.api_key = api_key
        self.host = host.rstrip('/')

    def history(self, symbol, exchange="NSE", interval="5m", start_date=None, end_date=None, max_retries=3):
        """Fetch historical data with retry logic and exponential backoff"""
        url = f"{self.host}/api/v1/history"
        payload = {
            "symbol": symbol,
            "exchange": exchange,
            "interval": interval,  # Fixed: was "resolution"
            "start_date": start_date,  # Fixed: was "from"
            "end_date": end_date,  # Fixed: was "to"
            "apikey": self.api_key
        }
        for attempt in range(max_retries):
            try:
                response = httpx.post(url, json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'success' and 'data' in data:
                        df = pd.DataFrame(data['data'])
                        if 'timestamp' in df.columns:
                            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
                        required_cols = ['open', 'high', 'low', 'close', 'volume']
                        for col in required_cols:
                            if col not in df.columns:
                                df[col] = 0
                        logger.debug(f"Successfully fetched {len(df)} rows for {symbol} on {exchange}")
                        return df
                    else:
                        error_msg = data.get('message', 'Unknown error')
                        if attempt < max_retries - 1:
                            wait_time = 2 ** attempt
                            logger.warning(f"History fetch failed for {symbol} (attempt {attempt+1}/{max_retries}): {error_msg}. Retrying in {wait_time}s...")
                            time_module.sleep(wait_time)
                            continue
                        logger.error(f"History fetch failed after {max_retries} attempts: {error_msg}")
                else:
                    error_text = response.text[:500] if response.text else "(empty)"
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(f"API call failed for {symbol} (HTTP {response.status_code}, attempt {attempt+1}/{max_retries}), retrying in {wait_time}s...")
                        time_module.sleep(wait_time)
                        continue
                    logger.error(f"History fetch failed after {max_retries} attempts (HTTP {response.status_code}): {error_text}")
            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"API timeout for {symbol} (attempt {attempt+1}/{max_retries}), retrying in {wait_time}s...")
                    time_module.sleep(wait_time)
                    continue
                logger.error(f"API timeout after {max_retries} attempts for {symbol}")
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"API Error for {symbol} (attempt {attempt+1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                    time_module.sleep(wait_time)
                    continue
                logger.error(f"API Error after {max_retries} attempts for {symbol}: {e}")
        
        return pd.DataFrame()

    def get_quote(self, symbol, exchange="NSE", max_retries=3):
        """Fetch real-time quote from Kite API via OpenAlgo"""
        url = f"{self.host}/api/v1/quotes"
        payload = {
            "symbol": symbol,
            "exchange": exchange,
            "apikey": self.api_key
        }
        
        for attempt in range(max_retries):
            try:
                response = httpx.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    # Check if response has content
                    if not response.text or len(response.text.strip()) == 0:
                        if attempt < max_retries - 1:
                            wait_time = 2 ** attempt
                            logger.warning(f"Quote API returned empty response for {symbol} (attempt {attempt+1}/{max_retries}). Retrying in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        logger.error(f"Quote API returned empty response after {max_retries} attempts for {symbol}")
                        return None
                    
                    try:
                        data = response.json()
                    except ValueError as json_err:
                        error_text = response.text[:200] if response.text else "(empty)"
                        if attempt < max_retries - 1:
                            wait_time = 2 ** attempt
                            logger.warning(f"Quote API returned non-JSON for {symbol} (attempt {attempt+1}/{max_retries}): {error_text}. Retrying in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        logger.error(f"Quote API returned non-JSON after {max_retries} attempts for {symbol}: {error_text}")
                        return None
                    
                    if data.get('status') == 'success' and 'data' in data:
                        quote_data = data['data']
                        # Ensure ltp is available
                        if 'ltp' in quote_data:
                            return quote_data
                        else:
                            logger.warning(f"Quote for {symbol} missing 'ltp' field. Available fields: {list(quote_data.keys())}")
                            return None
                    else:
                        error_msg = data.get('message', 'Unknown error')
                        if attempt < max_retries - 1:
                            wait_time = 2 ** attempt
                            logger.warning(f"Quote fetch failed for {symbol} (attempt {attempt+1}/{max_retries}): {error_msg}. Retrying in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        logger.error(f"Quote fetch failed after {max_retries} attempts: {error_msg}")
                else:
                    error_text = response.text[:500] if response.text else "(empty)"
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(f"Quote API call failed for {symbol} (HTTP {response.status_code}, attempt {attempt+1}/{max_retries}), retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    logger.error(f"Quote fetch failed after {max_retries} attempts (HTTP {response.status_code}): {error_text}")
            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Quote API timeout for {symbol} (attempt {attempt+1}/{max_retries}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Quote API timeout after {max_retries} attempts for {symbol}")
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Quote API Error for {symbol} (attempt {attempt+1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Quote API Error after {max_retries} attempts for {symbol}: {e}")
        
        return None  # Failed to fetch quote

    def get_instruments(self, exchange="NSE", max_retries=3):
        """Fetch instruments list"""
        url = f"{self.host}/instruments/{exchange}"
        for attempt in range(max_retries):
            try:
                response = httpx.get(url, timeout=30)
                if response.status_code == 200:
                    # Usually returns CSV text
                    from io import StringIO
                    return pd.read_csv(StringIO(response.text))
                else:
                    logger.warning(f"Instruments fetch failed (HTTP {response.status_code})")
                    time_module.sleep(1)
            except Exception as e:
                logger.error(f"Instruments fetch error: {e}")
                time_module.sleep(1)
        return pd.DataFrame()

    def placesmartorder(self, strategy, symbol, action, exchange, price_type, product, quantity, position_size):
        """Place smart order"""
        # #region agent log
        debug_log_path = "/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log"
        try:
            import json as json_module
            with open(debug_log_path, "a") as f:
                f.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"trading_utils.py:201","message":"placesmartorder() called","data":{"strategy":strategy,"symbol":symbol,"action":action,"exchange":exchange,"price_type":price_type,"product":product,"quantity":quantity,"position_size":position_size},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion
        
        # Correct endpoint is /api/v1/placesmartorder (not /api/v1/smartorder)
        url = f"{self.host}/api/v1/placesmartorder"

        payload = {
            "apikey": self.api_key,
            "strategy": strategy,
            "symbol": symbol,
            "action": action,  # Fixed: was "transaction_type"
            "exchange": exchange,
            "pricetype": price_type,  # Fixed: was "order_type"
            "product": product,
            "quantity": str(quantity),  # API expects string
            "position_size": str(position_size),  # API expects string
            "price": "0",
            "trigger_price": "0",
            "disclosed_quantity": "0"
        }
        
        # #region agent log
        try:
            with open(debug_log_path, "a") as f:
                f.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"trading_utils.py:220","message":"Before API call","data":{"url":url,"payload_keys":list(payload.keys())},"timestamp":int(time.time()*1000)}) + "\n")
        except: pass
        # #endregion
        
        try:
            response = httpx.post(url, json=payload, timeout=10)
            
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"trading_utils.py:225","message":"API response received","data":{"status_code":response.status_code,"content_length":len(response.content),"content_type":response.headers.get("content-type","unknown")},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
            
            if response.status_code == 200:
                # Handle response - may be JSON or empty
                try:
                    response_data = response.json()
                    # #region agent log
                    try:
                        with open(debug_log_path, "a") as f:
                            f.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"trading_utils.py:232","message":"Response parsed as JSON","data":{"has_orderid":"orderid" in response_data,"status":response_data.get("status")},"timestamp":int(time.time()*1000)}) + "\n")
                    except: pass
                    # #endregion
                    logger.info(f"[ENTRY] Order Placed: {response_data}")
                    return response_data
                except ValueError:
                    # Response is not JSON - might be empty or HTML
                    response_text = response.text[:200] if response.text else "(empty)"
                    # #region agent log
                    try:
                        with open(debug_log_path, "a") as f:
                            f.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"trading_utils.py:240","message":"Response not JSON","data":{"response_preview":response_text,"content_length":len(response.content)},"timestamp":int(time.time()*1000)}) + "\n")
                    except: pass
                    # #endregion
                    logger.warning(f"Order API returned non-JSON response (status 200): {response_text}")
                    # Return success indication even if response isn't JSON
                    return {"status": "success", "message": "Order placed (non-JSON response)"}
            else:
                error_text = response.text[:500] if response.text else "(empty)"
                # #region agent log
                try:
                    with open(debug_log_path, "a") as f:
                        f.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"trading_utils.py:248","message":"Order API error response","data":{"status_code":response.status_code,"error":error_text},"timestamp":int(time.time()*1000)}) + "\n")
                except: pass
                # #endregion
                logger.error(f"Order Failed (HTTP {response.status_code}): {error_text}")
                return {"status": "error", "message": f"HTTP {response.status_code}: {error_text}"}
        except Exception as e:
            # #region agent log
            try:
                with open(debug_log_path, "a") as f:
                    f.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"trading_utils.py:254","message":"Order API exception","data":{"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)}) + "\n")
            except: pass
            # #endregion
            logger.error(f"Order API Error: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return {"status": "error", "message": str(e)}
