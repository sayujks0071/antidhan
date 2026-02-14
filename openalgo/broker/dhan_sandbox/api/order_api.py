import json
import os

import httpx

from broker.dhan_sandbox.api.baseurl import get_url
from broker.dhan_sandbox.mapping.transform_data import (
    map_exchange,
    map_exchange_type,
    map_product_type,
    reverse_map_product_type,
    transform_data,
    transform_modify_order_data,
)
from database.auth_db import get_auth_token
from database.token_db import get_br_symbol, get_oa_symbol, get_symbol, get_token
from utils.httpx_client import get_httpx_client, request
from utils.logging import get_logger

logger = get_logger(__name__)


def get_api_response(endpoint, auth, method="GET", payload=""):
    """
    Helper function to make API requests to the Dhan Sandbox.

    Args:
        endpoint (str): The API endpoint (e.g., "/v2/orders").
        auth (str): The authentication token (Access Token).
        method (str, optional): HTTP method (GET, POST, PUT, DELETE). Defaults to "GET".
        payload (str, optional): JSON string payload for POST/PUT requests. Defaults to "".

    Returns:
        dict: The JSON response from the API, or an error dictionary.
    """
    AUTH_TOKEN = auth
    # api_key = os.getenv("BROKER_API_KEY")

    # Headers for the request
    headers = {
        "access-token": AUTH_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    url = get_url(endpoint)

    try:
        # Use the shared request function which includes retry logic for 500/429 errors
        # max_retries=3 is appropriate for handling transient server errors
        response = request(
            method,
            url,
            headers=headers,
            content=payload,
            max_retries=3
        )

        # Add status attribute for compatibility with existing codebase
        response.status = response.status_code

        # Parse the response JSON
        response_data = json.loads(response.text)

        # Check for API errors in the response
        if isinstance(response_data, dict):
            # Some Dhan API errors come in this format
            if response_data.get("status") == "failed" or response_data.get("status") == "error":
                error_data = response_data.get("data", {})
                if error_data:
                    error_code = list(error_data.keys())[0] if error_data else "unknown"
                    error_message = error_data.get(error_code, "Unknown error")
                    logger.error(f"API Error: {error_code} - {error_message}")
                    # Return the error response for further handling
                    return response_data

            # Other Dhan API errors might come in this format
            if response_data.get("errorType"):
                logger.error(
                    f"API Error: {response_data.get('errorCode')} - {response_data.get('errorMessage')}"
                )
                # Return the error response for further handling
                return response_data

        return response_data

    except Exception as e:
        # Handle connection or parsing errors
        logger.exception(f"Error in API request to {url}: {e}")
        return {"errorType": "ConnectionError", "errorMessage": str(e)}


def get_order_book(auth):
    """
    Fetch the order book.

    Args:
        auth (str): Authentication token.

    Returns:
        dict or list: The order book data or error response.
    """
    return get_api_response("/v2/orders", auth)


def get_trade_book(auth):
    """
    Fetch the trade book.

    Args:
        auth (str): Authentication token.

    Returns:
        dict or list: The trade book data or error response.
    """
    return get_api_response("/v2/trades", auth)


def get_positions(auth):
    """
    Fetch current positions.

    Args:
        auth (str): Authentication token.

    Returns:
        dict or list: The positions data or error response.
    """
    return get_api_response("/v2/positions", auth)


def get_holdings(auth):
    """
    Fetch holdings.

    Args:
        auth (str): Authentication token.

    Returns:
        dict or list: The holdings data or error response.
    """
    return get_api_response("/v2/holdings", auth)


def get_open_position(tradingsymbol, exchange, product, auth):
    """
    Get the net quantity of an open position for a specific symbol.

    Args:
        tradingsymbol (str): Trading symbol (OpenAlgo format).
        exchange (str): Exchange (e.g., NSE, MCX).
        product (str): Product type (e.g., MIS, NRML).
        auth (str): Authentication token.

    Returns:
        str: The net quantity as a string (e.g., "10", "-5", "0") or None on error.
    """
    # 1. Error handling for Invalid Token (Auth Token)
    if not auth:
        logger.error("Invalid Token: Authentication token is missing or empty")
        return None

    # Convert Trading Symbol from OpenAlgo Format to Broker Format Before Search in OpenPosition
    br_symbol = get_br_symbol(tradingsymbol, exchange)

    # 2. Error handling for SecurityId Required (Invalid Symbol)
    if not br_symbol:
        logger.error(f"SecurityId Required: Broker symbol not found for {tradingsymbol} {exchange}")
        return None

    positions_data = get_positions(auth)
    net_qty = "0"

    # Check if positions_data is an error response
    if isinstance(positions_data, dict) and (
        positions_data.get("errorType")
        or positions_data.get("status") == "failed"
        or positions_data.get("status") == "error"
    ):
        logger.error(
            f"Error getting positions for {tradingsymbol}: {positions_data.get('errorMessage', 'API Error')}"
        )
        return None

    # Only process if positions_data is valid and not an error
    if positions_data and isinstance(positions_data, list):
        for position in positions_data:
            if (
                position.get("tradingSymbol") == br_symbol
                and position.get("exchangeSegment") == map_exchange_type(exchange)
                and position.get("productType") == product
            ):
                net_qty = position.get("netQty", "0")
                break  # Assuming you need the first match

    return net_qty


def place_order_api(data, auth):
    """
    Place an order via the Dhan API.

    Args:
        data (dict): Order parameters. Must include 'symbol', 'exchange', 'action', 'quantity', 'pricetype', 'product'.
        auth (str): Authentication token.

    Returns:
        tuple: (response_object, response_dict, order_id)
            - response_object: The HTTP response object.
            - response_dict (dict): The parsed JSON response.
            - order_id (str or None): The generated Order ID. None if the order is rejected or failed.
    """
    # 1. Error handling for Invalid Token (Auth Token)
    if not auth:
        logger.error("Invalid Token: Authentication token is missing or empty")
        return None, {"status": "error", "message": "Invalid Token"}, None

    AUTH_TOKEN = auth
    BROKER_API_KEY = os.getenv("BROKER_API_KEY")
    data["apikey"] = BROKER_API_KEY

    # Get SecurityId (Token)
    token = get_token(data["symbol"], data["exchange"])

    # 2. Error handling for SecurityId Required
    if not token:
        logger.error(f"SecurityId Required: Token not found for {data['symbol']} {data['exchange']}")
        return None, {"status": "error", "message": "SecurityId Required"}, None

    newdata = transform_data(data, token)
    headers = {
        "access-token": AUTH_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = json.dumps(newdata)

    logger.debug(f"Placing order with payload: {payload}")

    url = get_url("/v2/orders")

    # 3. Automatic retry mechanism for 500-level API responses
    # Use the shared request function which includes retry logic for 500/429 errors
    # NOTE: The 'request' utility automatically retries 500-level errors and 429s up to max_retries.
    res = request(
        "POST",
        url,
        headers=headers,
        content=payload,
        max_retries=3
    )

    # Add status attribute for compatibility with existing codebase
    res.status = res.status_code

    try:
        response_data = json.loads(res.text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        return res, {"error": "Invalid JSON response"}, None

    logger.debug(f"Place order response: {response_data}")

    # Check if the API call was successful before accessing orderId
    orderid = None
    if res.status_code == 200 or res.status_code == 201:
        if response_data and "orderId" in response_data:
            # Check for immediate rejection in status
            order_status = response_data.get("orderStatus")
            if order_status in ["REJECTED", "FAILED"]:
                logger.error(
                    f"Order Rejected with ID {response_data['orderId']}: {response_data}"
                )
                orderid = None
                # Ensure failure reason is propagated
                if "message" not in response_data:
                    reason = response_data.get("remarks") or response_data.get(
                        "rejectReason"
                    )
                    if not reason and "data" in response_data:
                        reason = response_data["data"].get("rejectReason")

                    if reason:
                        response_data["message"] = f"Order Rejected: {reason}"
                    else:
                        response_data["message"] = "Order Rejected by Broker"
            else:
                orderid = response_data["orderId"]
        else:
            logger.error(f"orderId not found in response: {response_data}")
    else:
        logger.error(f"API call failed with status {res.status_code}: {response_data}")

    return res, response_data, orderid


def place_smartorder_api(data, auth):
    """
    Place a smart order (adaptive order based on current position).
    Used for closing positions or managing net quantity.

    Args:
        data (dict): Order parameters including 'position_size'.
        auth (str): Authentication token.

    Returns:
        tuple: (response_object, response_dict, order_id)
            - response_object: The HTTP response object.
            - response_dict (dict): The parsed JSON response.
            - order_id (str or None): The generated Order ID. None if the order is rejected or logic determined no action needed.
    """
    # 1. Error handling for Invalid Token (Auth Token)
    if not auth:
        logger.error("Invalid Token: Authentication token is missing or empty")
        return None, {"status": "error", "message": "Invalid Token"}, None

    AUTH_TOKEN = auth
    # BROKER_API_KEY = os.getenv("BROKER_API_KEY")
    # If no API call is made in this function then res will return None
    res = None

    # Extract necessary info from data
    symbol = data.get("symbol")
    exchange = data.get("exchange")

    # 2. Error handling for SecurityId Required
    token = get_token(symbol, exchange)
    if not token:
        logger.error(f"SecurityId Required: Token not found for {symbol} {exchange}")
        return None, {"status": "error", "message": "SecurityId Required"}, None

    product = data.get("product")
    position_size = int(data.get("position_size", "0"))

    # Get SecurityId (Token) - Check for invalid symbol early
    token = get_token(symbol, exchange)

    # 2. Error handling for SecurityId Required
    if not token:
        logger.error(f"SecurityId Required: Token not found for {symbol} {exchange}")
        return None, {"status": "error", "message": "SecurityId Required"}, None

    # Get current open position for the symbol
    open_pos_result = get_open_position(symbol, exchange, map_product_type(product), AUTH_TOKEN)

    # Handle error in getting position
    if open_pos_result is None:
        logger.error(f"Failed to get open position for {symbol}")
        # Return appropriate error - if auth was valid but API failed
        return None, {"status": "error", "message": "Failed to fetch open position"}, None

    current_position = int(open_pos_result)

    logger.info(f"position_size : {position_size}")
    logger.info(f"Open Position : {current_position}")

    # Determine action based on position_size and current_position
    action = None
    quantity = 0

    # If both position_size and current_position are 0, do nothing
    if position_size == 0 and current_position == 0 and int(data["quantity"]) != 0:
        action = data["action"]
        quantity = data["quantity"]
        res, response, orderid = place_order_api(data, AUTH_TOKEN)

        return res, response, orderid

    elif position_size == current_position:
        if int(data["quantity"]) == 0:
            response = {
                "status": "success",
                "message": "No OpenPosition Found. Not placing Exit order.",
            }
        else:
            response = {
                "status": "success",
                "message": "No action needed. Position size matches current position",
            }
        orderid = None
        return res, response, orderid  # res remains None as no API call was mad

    if position_size == 0 and current_position > 0:
        action = "SELL"
        quantity = abs(current_position)
    elif position_size == 0 and current_position < 0:
        action = "BUY"
        quantity = abs(current_position)
    elif current_position == 0:
        action = "BUY" if position_size > 0 else "SELL"
        quantity = abs(position_size)
    else:
        if position_size > current_position:
            action = "BUY"
            quantity = position_size - current_position
        elif position_size < current_position:
            action = "SELL"
            quantity = current_position - position_size

    if action:
        # Prepare data for placing the order
        order_data = data.copy()
        order_data["action"] = action
        order_data["quantity"] = str(quantity)

        # Place the order
        res, response, orderid = place_order_api(order_data, AUTH_TOKEN)

        return res, response, orderid


def close_all_positions(current_api_key, auth):
    """
    Close all open positions.

    Args:
        current_api_key (str): The user's API Key (OpenAlgo context).
        auth (str): Authentication token (Broker context).

    Returns:
        tuple: (response_dict, status_code)
    """
    AUTH_TOKEN = auth
    # Fetch the current open positions
    positions_response = get_positions(AUTH_TOKEN)
    logger.debug(f"Positions response for closing all: {positions_response}")

    # Check if the positions data is null or empty
    if positions_response is None or not positions_response:
        return {"message": "No Open Positions Found"}, 200

    if positions_response:
        # Loop through each position to close
        for position in positions_response:
            # Skip if net quantity is zero
            if int(position["netQty"]) == 0:
                continue

            # Determine action based on net quantity
            action = "SELL" if int(position["netQty"]) > 0 else "BUY"
            quantity = abs(int(position["netQty"]))

            # print(f"Trading Symbol : {position['tradingsymbol']}")
            # print(f"Exchange : {position['exchange']}")

            # get openalgo symbol to send to placeorder function
            symbol = get_symbol(position["securityId"], map_exchange(position["exchangeSegment"]))
            logger.info(f"The Symbol is {symbol}")

            # Prepare the order payload
            place_order_payload = {
                "apikey": current_api_key,
                "strategy": "Squareoff",
                "symbol": symbol,
                "action": action,
                "exchange": map_exchange(position["exchangeSegment"]),
                "pricetype": "MARKET",
                "product": reverse_map_product_type(position["productType"]),
                "quantity": str(quantity),
            }

            logger.debug(f"Close position payload: {place_order_payload}")

            # Place the order to close the position
            _, api_response, _ = place_order_api(place_order_payload, AUTH_TOKEN)

            logger.debug(f"Close position response: {api_response}")

            # Note: Ensure place_order_api handles any errors and logs accordingly

    return {"status": "success", "message": "All Open Positions SquaredOff"}, 200


def cancel_order(orderid, auth):
    """
    Cancel a specific order.

    Args:
        orderid (str): The ID of the order to cancel.
        auth (str): Authentication token.

    Returns:
        tuple: (response_dict, status_code)
    """
    # Assuming you have a function to get the authentication token
    AUTH_TOKEN = auth

    # Set up the request headers
    headers = {
        "access-token": AUTH_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Construct the URL for deleting the order
    url = get_url(f"/v2/orders/{orderid}")

    # Make the DELETE request using shared request function with retry logic
    res = request(
        "DELETE",
        url,
        headers=headers,
        max_retries=3
    )

    # Add status attribute for compatibility with existing codebase
    res.status = res.status_code

    # Parse the response
    data = json.loads(res.text)

    # Check if the request was successful
    if data:
        # Return a success response
        return {"status": "success", "orderid": orderid}, 200
    else:
        # Return an error response
        return {
            "status": "error",
            "message": data.get("message", "Failed to cancel order"),
        }, res.status


def modify_order(data, auth):
    """
    Modify an existing order.

    Args:
        data (dict): Order modification parameters (must include 'orderid').
        auth (str): Authentication token.

    Returns:
        tuple: (response_dict, status_code)
    """
    # Assuming you have a function to get the authentication token
    AUTH_TOKEN = auth
    BROKER_API_KEY = os.getenv("BROKER_API_KEY")
    data["apikey"] = BROKER_API_KEY

    orderid = data["orderid"]
    transformed_order_data = transform_modify_order_data(
        data
    )  # You need to implement this function

    # Set up the request headers
    headers = {
        "access-token": AUTH_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = json.dumps(transformed_order_data)

    logger.debug(f"Modify order payload: {payload}")

    # Construct the URL for modifying the order
    url = get_url(f"/v2/orders/{orderid}")

    # Make the PUT request using shared request function with retry logic
    res = request(
        "PUT",
        url,
        headers=headers,
        content=payload,
        max_retries=3
    )

    # Add status attribute for compatibility with existing codebase
    res.status = res.status_code

    # Parse the response
    data = json.loads(res.text)
    logger.debug(f"Modify order response: {data}")
    # return {"status": "error", "message": data.get("message", "Failed to modify order")}, res.status

    if data["orderId"]:
        return {"status": "success", "orderid": data["orderId"]}, 200
    else:
        return {
            "status": "error",
            "message": data.get("message", "Failed to modify order"),
        }, res.status


def cancel_all_orders_api(data, auth):
    """
    Cancel all pending orders.

    Args:
        data (dict): Request data (unused).
        auth (str): Authentication token.

    Returns:
        tuple: (canceled_orders_list, failed_cancellations_list)
    """
    # Get the order book
    AUTH_TOKEN = auth
    order_book_response = get_order_book(AUTH_TOKEN)
    logger.debug(f"Order book for cancel all: {order_book_response}")
    if order_book_response is None:
        return [], []  # Return empty lists indicating failure to retrieve the order book

    # Filter orders that are in 'open' or 'trigger_pending' state
    orders_to_cancel = [
        order for order in order_book_response if order["orderStatus"] in ["PENDING"]
    ]
    logger.info(f"Orders to cancel: {orders_to_cancel}")
    canceled_orders = []
    failed_cancellations = []

    # Cancel the filtered orders
    for order in orders_to_cancel:
        orderid = order["orderId"]
        cancel_response, status_code = cancel_order(orderid, AUTH_TOKEN)
        if status_code == 200:
            canceled_orders.append(orderid)
        else:
            failed_cancellations.append(orderid)

    return canceled_orders, failed_cancellations
