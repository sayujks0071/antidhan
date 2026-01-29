import os
import logging
import pytz
import json
import time as time_module
from pathlib import Path
from datetime import datetime, time
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

    market_start = time(9, 15)
    market_end = time(15, 30)
    current_time = now.time()

    return market_start <= current_time <= market_end

def calculate_intraday_vwap(df):
    """
    Calculate VWAP resetting daily.
    Expects DataFrame with 'datetime' (or index), 'close', 'high', 'low', 'volume'.
    """
    df = df.copy()
    if 'datetime' not in df.columns and isinstance(df.index, pd.DatetimeIndex):
        df['datetime'] = df.index

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

    def history(self, symbol, exchange="NSE", interval="5m", start_date=None, end_date=None):
        """Fetch historical data with retries"""
        url = f"{self.host}/api/v1/history"
        payload = {
            "symbol": symbol,
            "exchange": exchange,
            "resolution": interval,
            "from": start_date,
            "to": end_date,
            "apikey": self.api_key
        }

        for attempt in range(3):
            try:
                response = httpx.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'success' and 'data' in data:
                        df = pd.DataFrame(data['data'])
                        return df
                logger.warning(f"History fetch attempt {attempt+1} failed: {response.text if response else 'No Response'}")
            except Exception as e:
                logger.warning(f"API Error attempt {attempt+1}: {e}")

            time_module.sleep(1) # Backoff

        logger.error(f"History fetch failed after 3 attempts for {symbol}")
        return pd.DataFrame() # Empty DF on failure

    def placesmartorder(self, strategy, symbol, action, exchange, price_type, product, quantity, position_size):
        """Place order with retries"""
        url = f"{self.host}/api/v1/smartorder"

        payload = {
            "strategy": strategy,
            "symbol": symbol,
            "transaction_type": action,
            "exchange": exchange,
            "order_type": price_type,
            "product": product,
            "quantity": quantity,
            "apikey": self.api_key
        }

        for attempt in range(3):
            try:
                response = httpx.post(url, json=payload, timeout=5)
                if response.status_code == 200:
                    logger.info(f"Order Placed: {response.json()}")
                    return response.json()
                else:
                    logger.warning(f"Order attempt {attempt+1} failed: {response.text}")
            except Exception as e:
                logger.warning(f"Order API Error attempt {attempt+1}: {e}")

            time_module.sleep(1)

        logger.error(f"Order placement failed after 3 attempts for {symbol}")
        return None
