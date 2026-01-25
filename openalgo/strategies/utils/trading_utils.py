import os
import logging
import pytz
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
    Simple in-memory position manager to prevent duplicate orders.
    """
    def __init__(self, symbol):
        self.symbol = symbol
        self.position = 0 # Net quantity
        self.entry_price = 0.0

    def update_position(self, qty, price, side):
        """
        Update position state.
        side: 'BUY' or 'SELL'
        """
        if side.upper() == 'BUY':
            if self.position == 0:
                self.entry_price = price
            self.position += qty
        elif side.upper() == 'SELL':
            if self.position == 0:
                self.entry_price = price # Short entry
            self.position -= qty

        logger.info(f"Position Updated for {self.symbol}: {self.position} @ {self.entry_price}")

    def has_position(self):
        return self.position != 0

class APIClient:
    """
    Fallback API Client using httpx if openalgo package is missing.
    """
    def __init__(self, api_key, host="http://127.0.0.1:5001"):
        self.api_key = api_key
        self.host = host.rstrip('/')

    def history(self, symbol, exchange="NSE", interval="5m", start_date=None, end_date=None):
        """Fetch historical data"""
        url = f"{self.host}/api/v1/history"
        payload = {
            "symbol": symbol,
            "exchange": exchange,
            "resolution": interval,
            "from": start_date,
            "to": end_date,
            "apikey": self.api_key
        }
        try:
            response = httpx.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success' and 'data' in data:
                    df = pd.DataFrame(data['data'])
                    # Clean up if needed, ensure columns match
                    return df
            logger.error(f"History fetch failed: {response.text}")
        except Exception as e:
            logger.error(f"API Error: {e}")
        return pd.DataFrame() # Empty DF on failure

    def placesmartorder(self, strategy, symbol, action, exchange, price_type, product, quantity, position_size):
        """Place order"""
        url = f"{self.host}/api/v1/orders" # Assuming standard endpoint, might vary
        # Note: 'placesmartorder' implies logic on server, but we'll map to simple order for fallback
        # Or if the server supports smart orders:
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
        try:
            response = httpx.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                logger.info(f"Order Placed: {response.json()}")
                return response.json()
            else:
                logger.error(f"Order Failed: {response.text}")
        except Exception as e:
            logger.error(f"Order API Error: {e}")
