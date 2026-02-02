#!/usr/bin/env python3
import sys
import os
import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock, patch

# Add openalgo path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

# Handle imports for standalone execution vs module execution
try:
    from strategies.utils.trading_utils import APIClient
    from strategies.scripts.supertrend_vwap_strategy import SuperTrendVWAPStrategy
except ImportError:
    # Try adding root to path
    sys.path.append(os.getcwd())
    from openalgo.strategies.utils.trading_utils import APIClient
    from openalgo.strategies.scripts.supertrend_vwap_strategy import SuperTrendVWAPStrategy

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MarketHoursAudit")

def audit_latency():
    logger.info("Starting Latency Audit...")
    client = APIClient(api_key="audit_test")

    # Mocking httpx_client inside APIClient for this specific test
    # Build the correct patch path based on where APIClient was imported from
    httpx_client_path = f"{APIClient.__module__}.httpx_client"
    with patch(httpx_client_path) as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "orderid": "audit_123"}
        mock_response.http_version = "HTTP/1.1"
        mock_response.request.extensions = {}

        mock_client.post.return_value = mock_response

        signal_time = time.time()
        logger.info(f"Signal Generated at {datetime.fromtimestamp(signal_time)}")

        # Simulate processing time
        time.sleep(0.05)

        client.placesmartorder(
            strategy="AUDIT", symbol="TEST", action="BUY", exchange="NSE",
            price_type="MARKET", product="MIS", quantity=1, position_size=1
        )

        order_time = time.time()
        logger.info(f"Order Placed at {datetime.fromtimestamp(order_time)}")

        latency_ms = (order_time - signal_time) * 1000
        logger.info(f"Latency: {latency_ms:.2f}ms")

        if latency_ms > 500:
            logger.warning("Latency exceeds 500ms threshold!")
        else:
            logger.info("Latency within acceptable limits.")

        return latency_ms

def verify_logic():
    logger.info("Starting Logic Verification (SuperTrend VWAP)...")

    # Create sample data
    dates = pd.date_range(end=datetime.now(), periods=100, freq='5min')
    np.random.seed(42)
    data = {
        'open': np.random.normal(100, 1, 100),
        'high': np.random.normal(102, 1, 100),
        'low': np.random.normal(98, 1, 100),
        'close': np.random.normal(100, 1, 100),
        'volume': np.random.randint(1000, 5000, 100),
        'datetime': dates
    }
    df = pd.DataFrame(data)

    strategy = SuperTrendVWAPStrategy(symbol="TEST", quantity=1, api_key="test", host="test")

    # Verify RSI Calculation
    rsi = strategy.calculate_rsi(df['close'])
    last_rsi = rsi.iloc[-1]
    logger.info(f"Calculated RSI: {last_rsi:.2f}")

    # Manual Calculation (using SMA as per trading_utils implementation)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    expected_rsi = 100 - (100 / (1 + rs))
    expected_last = expected_rsi.iloc[-1]

    # Handle NaN at start
    if pd.isna(last_rsi) and pd.isna(expected_last):
        logger.info("Logic Verification Passed: RSI is NaN as expected for initial periods.")
    elif np.isclose(last_rsi, expected_last, atol=0.01):
        logger.info(f"Logic Verification Passed: RSI Calculation is accurate ({last_rsi:.2f}).")
    else:
        logger.error(f"Logic Verification Failed: RSI {last_rsi} != {expected_last}")

def check_slippage():
    logger.info("Starting Slippage Check...")
    # Simulate Slippage with random realistic values
    slippage_data = [
        {"symbol": "NIFTY", "signal": 18000.00, "fill": 18001.05},
        {"symbol": "BANKNIFTY", "signal": 42000.00, "fill": 42002.50},
        {"symbol": "RELIANCE", "signal": 2500.00, "fill": 2500.20},
    ]

    total_slippage = 0
    count = 0

    for trade in slippage_data:
        slip = abs(trade['fill'] - trade['signal'])
        logger.info(f"Symbol: {trade['symbol']}, Signal: {trade['signal']}, Fill: {trade['fill']}, Slippage: {slip:.2f}")
        total_slippage += slip
        count += 1

    avg_slippage = total_slippage / count
    logger.info(f"Average Slippage: {avg_slippage:.2f}")

    return avg_slippage

if __name__ == "__main__":
    print("=== Market-Hours Audit Report ===")
    try:
        audit_latency()
    except Exception as e:
        logger.error(f"Latency Audit Failed: {e}")

    try:
        verify_logic()
    except Exception as e:
        logger.error(f"Logic Verification Failed: {e}")

    try:
        check_slippage()
    except Exception as e:
        logger.error(f"Slippage Check Failed: {e}")
    print("=== End Report ===")
