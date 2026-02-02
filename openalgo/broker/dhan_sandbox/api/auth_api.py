import json
import os

import httpx

from broker.dhan_sandbox.api.baseurl import BASE_URL, get_url
from utils.httpx_client import get_httpx_client


def authenticate_broker(code):
    """
    Authenticate with the broker using the provided code.

    Args:
        code (str): The authentication code received from the broker's redirect.

    Returns:
        tuple: (access_token, error_message)
               access_token (str): The access token if successful, else None.
               error_message (str): Error message if failed, else None.
    """
    try:
        BROKER_API_KEY = os.getenv("BROKER_API_KEY")
        BROKER_API_SECRET = os.getenv("BROKER_API_SECRET")
        REDIRECT_URL = os.getenv("REDIRECT_URL")

        # Get the shared httpx client with connection pooling
        client = get_httpx_client()

        # Your authentication implementation here
        # For now, returning API secret as a placeholder like the original code
        return BROKER_API_SECRET, None

        if response.status_code == 200:
            response_data = response.json()
            if "access_token" in response_data:
                return response_data["access_token"], None
            else:
                return (
                    None,
                    "Authentication succeeded but no access token was returned. Please check the response.",
                )
        else:
            # Parsing the error message from the API response
            error_detail = response.json()  # Assuming the error is in JSON format
            error_messages = error_detail.get("errors", [])
            detailed_error_message = "; ".join([error["message"] for error in error_messages])
            return (
                None,
                f"API error: {error_messages}"
                if detailed_error_message
                else "Authentication failed. Please try again.",
            )
    except Exception as e:
        return None, f"An exception occurred: {str(e)}"
