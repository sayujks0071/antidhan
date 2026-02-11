import sys
import os
import pandas as pd
from datetime import datetime, timedelta
import logging

# Add path to repo root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Add path to openalgo package to allow 'import utils'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'openalgo')))

# Configure Logging
logging.basicConfig(level=logging.DEBUG)

from openalgo.strategies.utils.trading_utils import APIClient

def test_history_fetching():
    client = APIClient(api_key="TEST_KEY")

    print("Testing APIClient.history split logic...")

    symbol = "SBIN"
    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    print(f"Requesting {start_date} to {end_date}")

    try:
        df = client.history(symbol, start_date=start_date, end_date=end_date)
        print("Result Type:", type(df))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_history_fetching()
