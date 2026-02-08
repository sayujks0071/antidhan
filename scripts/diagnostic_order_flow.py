#!/usr/bin/env python3
"""
Diagnostic script to simulate order flow and verify response handling.
Attempts to place 5 different order types in the Dhan Sandbox.
"""
import os
import sys
import logging
import json
from unittest.mock import MagicMock, patch

# Add repository root to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(repo_root)
sys.path.append(os.path.join(repo_root, 'openalgo'))

# Set dummy environment variables to avoid startup errors
db_path = '/tmp/test_settings.db'
if os.path.exists(db_path):
    os.remove(db_path)
os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'
os.environ['BROKER_API_KEY'] = 'test_key'
os.environ['BROKER_API_SECRET'] = 'test_secret'
os.environ['API_KEY_PEPPER'] = '01234567890123456789012345678901'  # 32 chars

# Mock extensions to avoid DB issues during import of other modules that might use them
sys.modules['extensions'] = MagicMock()
sys.modules['database.telegram_db'] = MagicMock()
sys.modules['database.analyzer_db'] = MagicMock()

# Now import the service and DB utils using top-level names as the app does
from services.place_smart_order_service import place_smart_order
from utils.logging import get_logger
from database.settings_db import init_db as init_settings_db
import broker.dhan_sandbox.api.order_api
import database.token_db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = get_logger(__name__)

def test_order_flow():
    logger.info("Starting Order Flow Simulation")

    # Initialize Settings DB
    try:
        init_settings_db()
        logger.info("Settings DB initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize Settings DB: {e}")

    # Mock Auth Token and API Key
    mock_auth_token = "MOCK_AUTH_TOKEN"
    mock_api_key = "MOCK_API_KEY"
    broker_name = "dhan_sandbox"

    # Define 5 order types to test
    order_scenarios = [
        {
            "type": "LIMIT",
            "data": {
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "BUY",
                "product": "MIS",
                "pricetype": "LIMIT",
                "quantity": "1",
                "price": "500",
                "trigger_price": "0",
                "disclosed_quantity": "0",
                "strategy": "TEST_STRATEGY",
                "position_size": "0"
            }
        },
        {
            "type": "MARKET",
            "data": {
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "BUY",
                "product": "MIS",
                "pricetype": "MARKET",
                "quantity": "1",
                "price": "0",
                "trigger_price": "0",
                "disclosed_quantity": "0",
                "strategy": "TEST_STRATEGY",
                "position_size": "0"
            }
        },
        {
            "type": "STOP_LOSS",
            "data": {
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "SELL",
                "product": "MIS",
                "pricetype": "SL",
                "quantity": "1",
                "price": "490",
                "trigger_price": "495",
                "disclosed_quantity": "0",
                "strategy": "TEST_STRATEGY",
                "position_size": "0"
            }
        },
        {
            "type": "STOP_LOSS_MARKET",
            "data": {
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "SELL",
                "product": "MIS",
                "pricetype": "SL-M",
                "quantity": "1",
                "price": "0",
                "trigger_price": "495",
                "disclosed_quantity": "0",
                "strategy": "TEST_STRATEGY",
                "position_size": "0"
            }
        },
        {
            "type": "BRACKET_ORDER",
            "data": {
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "BUY",
                "product": "BO",
                "pricetype": "LIMIT",
                "quantity": "1",
                "price": "500",
                "trigger_price": "0",
                "disclosed_quantity": "0",
                "strategy": "TEST_STRATEGY",
                "position_size": "0"
            }
        }
    ]

    # Patch modules using the paths they are imported as
    with patch('broker.dhan_sandbox.api.order_api.request') as mock_request, \
         patch('database.token_db.get_token', return_value="12345"), \
         patch('services.place_smart_order_service.async_log_order') as mock_log:

        # Configure mock response for "Market Closed" rejection
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "status": "failed",
            "remarks": "Market is Closed",
            "data": {"rejectReason": "Market is Closed"},
            "orderId": "123456",
            "orderStatus": "REJECTED"
        })
        mock_response.json.return_value = json.loads(mock_response.text)
        mock_request.return_value = mock_response

        for scenario in order_scenarios:
            logger.info(f"--- Testing {scenario['type']} Order ---")
            order_data = scenario['data']
            order_data['apikey'] = mock_api_key

            try:
                success, response, status_code = place_smart_order(
                    order_data=order_data,
                    auth_token=mock_auth_token,
                    api_key=mock_api_key,
                    broker=broker_name
                )

                logger.info(f"Success: {success}")
                logger.info(f"Status Code: {status_code}")
                logger.info(f"Response: {response}")

                if success is False:
                    if "Order Rejected" in str(response) or "Market is Closed" in str(response):
                            logger.info("✅ Verified: Order correctly identified as rejected/failed.")
                    else:
                            logger.info(f"Verified: Order failed as expected, but message was: {response}")
                elif response.get("status") == "error":
                        logger.info(f"Verified: Order failed logically: {response}")
                else:
                    # Check for rejection in response
                    if response.get("message", "").startswith("Order Rejected"):
                         logger.info("✅ Verified: Order correctly identified as rejected/failed.")
                    else:
                        logger.warning(f"Unexpected Success! Response: {response}")

            except Exception as e:
                logger.error(f"Exception during test: {e}")

if __name__ == "__main__":
    test_order_flow()
