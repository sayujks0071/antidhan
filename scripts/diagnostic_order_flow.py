import os
import sys
import logging
import json

# Setup paths
script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, '../openalgo'))
sys.path.insert(0, repo_root)

# Mock environment variables required for imports
os.environ.setdefault('BROKER_API_KEY', 'test_api_key')
os.environ.setdefault('API_KEY_PEPPER', '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef') # 64 chars
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:') # Use in-memory DB to avoid config errors

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DiagnosticOrderFlow")

try:
    from broker.dhan_sandbox.api.order_api import place_order_api, get_order_book
except ImportError as e:
    logger.error(f"Import Error: {e}")
    # Try adding parent directory if openalgo is root
    sys.path.insert(0, os.path.abspath(os.path.join(script_dir, '..')))
    try:
        from openalgo.broker.dhan_sandbox.api.order_api import place_order_api, get_order_book
    except ImportError as e2:
        logger.error(f"Retry Import Error: {e2}")
        sys.exit(1)

def run_diagnostic():
    logger.info("Starting Order Flow Diagnostic...")

    # We use a dummy auth token.
    # If the Dhan Sandbox API validates it, it will fail.
    # But we are testing the "Attempt" and how the CODE handles the response.
    auth_token = "diagnostic_token"

    order_types = [
        {"pricetype": "LIMIT", "product": "MIS", "price": 100},
        {"pricetype": "MARKET", "product": "MIS", "price": 0},
        {"pricetype": "SL", "product": "MIS", "price": 100, "trigger_price": 99},
        {"pricetype": "SL-M", "product": "MIS", "price": 0, "trigger_price": 99},
        {"pricetype": "LIMIT", "product": "BO", "price": 100, "trigger_price": 99} # Bracket
    ]

    symbol = "SBIN"
    exchange = "NSE"

    results = []

    for i, order in enumerate(order_types):
        logger.info(f"--- Placing Order {i+1}: {order['pricetype']} / {order['product']} ---")

        payload = {
            "symbol": symbol,
            "exchange": exchange,
            "action": "BUY",
            "quantity": 1,
            "pricetype": order["pricetype"],
            "product": order["product"],
            "price": order["price"],
            "trigger_price": order.get("trigger_price", 0),
            "disclosed_quantity": 0,
            "validity": "DAY",
            "amo": False
        }

        try:
            # place_order_api(data, auth)
            # This will make an HTTP request to https://sandbox.dhan.co/v2/orders
            res, response, orderid = place_order_api(payload, auth_token)

            status_code = res.status_code if hasattr(res, 'status_code') else getattr(res, 'status', 'Unknown')
            logger.info(f"Response Status: {status_code}")
            logger.info(f"Response Body: {response}")

            results.append({
                "type": order["pricetype"],
                "status": status_code,
                "response": response,
                "orderid": orderid
            })

            if orderid:
                logger.info(f"Order ID: {orderid}")
            else:
                logger.info("No Order ID returned (Expected if auth failed or market closed/rejected)")

        except Exception as e:
            logger.error(f"Exception placing order: {e}", exc_info=True)
            results.append({
                "type": order["pricetype"],
                "error": str(e)
            })

    logger.info("--- Verifying Orderbook ---")
    try:
        # get_order_book(auth)
        # It calls /v2/orders GET
        orderbook = get_order_book(auth_token)

        logger.info(f"Orderbook Type: {type(orderbook)}")

        if isinstance(orderbook, list):
            logger.info(f"Orderbook contains {len(orderbook)} orders.")
            for order in orderbook:
                logger.info(f" - ID: {order.get('orderId')}, Status: {order.get('orderStatus')}, Symbol: {order.get('tradingSymbol')}")
        elif isinstance(orderbook, dict):
             logger.info(f"Orderbook returned dictionary: {orderbook}")
             if 'errorType' in orderbook or 'status' == 'failure':
                 logger.info("Orderbook fetch failed as expected with dummy token.")
        else:
            logger.info(f"Orderbook response: {orderbook}")

    except Exception as e:
        logger.error(f"Exception fetching orderbook: {e}", exc_info=True)

    logger.info("Diagnostic completed.")

    # Save results to file for inspection
    with open("order_flow_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

if __name__ == "__main__":
    run_diagnostic()
