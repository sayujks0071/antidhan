#!/usr/bin/env python
"""Test script to check what the history API returns"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openalgo import api
import pandas as pd
from datetime import datetime, timedelta
import json

# Initialize client
api_key = os.getenv("OPENALGO_APIKEY", "YOUR_OPENALGO_APIKEY")
client = api(api_key=api_key, host="http://127.0.0.1:5001")

# Test fetching history for RELIANCE
end_date = datetime.now()
start_date = end_date - timedelta(days=5)

print("Testing history API call...")
print(f"Symbol: RELIANCE")
print(f"Exchange: NSE")
print(f"Interval: 5m")
print(f"Start Date: {start_date.strftime('%Y-%m-%d')}")
print(f"End Date: {end_date.strftime('%Y-%m-%d')}")
print("\n" + "="*80 + "\n")

response = client.history(
    symbol="RELIANCE",
    exchange="NSE",
    interval="5m",
    start_date=start_date.strftime("%Y-%m-%d"),
    end_date=end_date.strftime("%Y-%m-%d")
)

print("Response type:", type(response))
print("\n" + "="*80 + "\n")

if isinstance(response, dict):
    print("Response is a dictionary with keys:", list(response.keys()))
    print("\nFull response:")
    print(json.dumps(response, indent=2, default=str))

    if 'data' in response:
        print("\n" + "="*80 + "\n")
        print("'data' key type:", type(response['data']))
        print("'data' content:", response['data'])

        if response['data']:
            print("\n" + "="*80 + "\n")
            print("Converting to DataFrame...")
            df = pd.DataFrame(response['data'])
            print("DataFrame shape:", df.shape)
            print("DataFrame columns:", list(df.columns))
            print("\nFirst few rows:")
            print(df.head())
        else:
            print("\n⚠️ The 'data' field is empty!")
    else:
        print("\n⚠️ No 'data' key in response!")

elif isinstance(response, pd.DataFrame):
    print("Response is already a DataFrame!")
    print("Shape:", response.shape)
    print("Columns:", list(response.columns))
    print("\nFirst few rows:")
    print(response.head())
else:
    print("Unexpected response type!")
    print("Response:", response)
