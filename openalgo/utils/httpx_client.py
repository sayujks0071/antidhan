"""
Shared httpx client module with connection pooling support for all broker APIs
with automatic protocol negotiation (HTTP/2 when available, HTTP/1.1 fallback).
Includes Retry-with-Backoff logic for robust error handling.
"""

import os
import time
from functools import wraps
from typing import Optional
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from utils.logging import get_logger

# Set up logging
logger = get_logger(__name__)

# Global httpx client for connection pooling
_httpx_client = None


def get_httpx_client() -> httpx.Client:
    """
    Returns an HTTP client with automatic protocol negotiation.
    The client will use HTTP/2 when the server supports it,
    otherwise automatically falls back to HTTP/1.1.

    Returns:
        httpx.Client: A configured HTTP client with protocol auto-negotiation
    """
    global _httpx_client

    if _httpx_client is None:
        _httpx_client = _create_http_client()
        logger.info(
            "Created HTTP client with automatic protocol negotiation (HTTP/2 preferred, HTTP/1.1 fallback)"
        )
    return _httpx_client


def retry_with_backoff(max_retries: int = 3, backoff_factor: float = 0.5):
    """
    Decorator to add retry with backoff logic to a function.
    Handles general exceptions and transient failures.
    For HTTP-specific retries (429/500), use the `request` function.

    Args:
        max_retries: Number of retries on failure (default 3)
        backoff_factor: Factor for exponential backoff (default 0.5)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = backoff_factor * (2**attempt)
                        logger.warning(
                            f"Function {func.__name__} failed: {e}. Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
            # If we exhausted retries, raise the last exception
            logger.error(f"Function {func.__name__} failed after {max_retries} retries: {last_exception}")
            raise last_exception
        return wrapper
    return decorator


def request(
    method: str, url: str, max_retries: int = 3, backoff_factor: float = 0.5, **kwargs
) -> httpx.Response:
    """
    Make an HTTP request using the shared client with automatic protocol negotiation.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: URL to request
        max_retries: Number of retries on failure (default 3)
        backoff_factor: Factor for exponential backoff (default 0.5)
        **kwargs: Additional arguments to pass to the request

    Returns:
        httpx.Response: The HTTP response

    Raises:
        httpx.HTTPError: If the request fails
    """
    try:
        from flask import g
    except ImportError:
        g = None

    client = get_httpx_client()

    last_exception = None
    response = None

    for attempt in range(max_retries + 1):
        try:
            # Track actual broker API call time for latency monitoring
            broker_api_start = time.time()
            response = client.request(method, url, **kwargs)
            broker_api_end = time.time()

            # Check for server errors or rate limits if retries are enabled
            if max_retries > 0 and (
                response.status_code >= 500 or response.status_code == 429
            ):
                if attempt < max_retries:
                    # Calculate default backoff
                    wait_time = backoff_factor * (2**attempt)

                    # Check for Retry-After header
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            retry_wait = 0.0
                            if retry_after.isdigit():
                                retry_wait = float(retry_after)
                            else:
                                # Parse HTTP date
                                retry_date = parsedate_to_datetime(retry_after)
                                if retry_date:
                                    # If naive, assume UTC as per HTTP spec
                                    if retry_date.tzinfo is None:
                                        retry_date = retry_date.replace(tzinfo=timezone.utc)

                                    now = datetime.now(retry_date.tzinfo)
                                    retry_wait = (retry_date - now).total_seconds()

                            # Use the larger of the two, but cap Retry-After at 60s
                            if retry_wait > 0:
                                capped_retry_wait = min(retry_wait, 60.0)
                                wait_time = max(wait_time, capped_retry_wait)
                                logger.info(f"Respecting Retry-After header: {retry_wait:.2f}s (capped/used: {wait_time:.2f}s)")
                        except Exception as e:
                             logger.warning(f"Failed to parse Retry-After header '{retry_after}': {e}")

                    logger.warning(
                        f"Request to {url} failed (HTTP {response.status_code}). Retrying in {wait_time:.2f}s..."
                    )
                    time.sleep(wait_time)
                    continue

            # If we get here, either success or non-retriable error
            # Store broker API time in Flask's g object for latency tracking
            try:
                if hasattr(g, "latency_tracker"):
                    broker_api_time_ms = (broker_api_end - broker_api_start) * 1000
                    g.broker_api_time = broker_api_time_ms
                    logger.debug(f"Broker API call took {broker_api_time_ms:.2f}ms")
            except RuntimeError:
                # Working outside of application context
                pass

            # Log the actual HTTP version used (info level for visibility)
            if response.http_version:
                logger.info(
                    f"Request used {response.http_version} - URL: {url[:50]}..."
                )

            return response

        except httpx.RequestError as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = backoff_factor * (2**attempt)
                logger.warning(
                    f"Request to {url} failed: {e}. Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                logger.error(
                    f"Request to {url} failed after {max_retries} retries: {e}"
                )
                raise last_exception

    # Should only reach here if max_retries > 0 and we exhausted retries on status codes
    return response


# Shortcut methods for common HTTP methods
def get(url: str, **kwargs) -> httpx.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> httpx.Response:
    return request("POST", url, **kwargs)


def put(url: str, **kwargs) -> httpx.Response:
    return request("PUT", url, **kwargs)


def delete(url: str, **kwargs) -> httpx.Response:
    return request("DELETE", url, **kwargs)


def _create_http_client() -> httpx.Client:
    """
    Create a new HTTP client with automatic protocol negotiation and latency tracking.
    Enables both HTTP/2 and HTTP/1.1, letting httpx choose the best protocol.

    Returns:
        httpx.Client: A configured HTTP client with protocol auto-negotiation and timing hooks
    """
    try:
        from flask import g
    except ImportError:
        g = None

    # Event hooks for tracking broker API timing
    def log_request(request):
        """Hook called before request is sent"""
        request.extensions["start_time"] = time.time()
        logger.debug(f"Starting request to {request.url}")

    def log_response(response):
        """Hook called after response is received"""
        try:
            start_time = response.request.extensions.get("start_time")
            if start_time:
                duration_ms = (time.time() - start_time) * 1000

                # Store broker API time in Flask's g object for latency tracking
                try:
                    from flask import has_request_context
                    if g and has_request_context() and hasattr(g, "latency_tracker"):
                        g.broker_api_time = duration_ms
                        logger.debug(f"Broker API call took {duration_ms:.2f}ms")
                except (ImportError, RuntimeError, AttributeError):
                    # Not in Flask request context or g not available
                    pass

                logger.debug(f"Request completed in {duration_ms:.2f}ms")
        except Exception as e:
            logger.exception(f"Error in response hook: {e}")

    try:
        # Detect if running in standalone mode (Docker/production) vs integrated mode (local dev)
        # In standalone mode, disable HTTP/2 to avoid protocol negotiation issues
        app_mode = os.environ.get("APP_MODE", "integrated").strip().strip("'\"")
        is_standalone = app_mode == "standalone"

        # Disable HTTP/2 in standalone/Docker environments to avoid protocol negotiation issues
        http2_enabled = not is_standalone

        client = httpx.Client(
            http2=http2_enabled,  # Disable HTTP/2 in standalone mode, enable in integrated mode
            http1=True,  # Always enable HTTP/1.1 for compatibility
            timeout=120.0,  # Increased timeout for large historical data requests
            limits=httpx.Limits(
                max_keepalive_connections=20,  # Balanced for most broker APIs
                max_connections=50,  # Reasonable max without overloading
                keepalive_expiry=120.0,  # 2 minutes - good balance
            ),
            # Add verify parameter to handle SSL/TLS issues in standalone mode
            verify=True,  # Can be set to False for debugging SSL issues (not recommended for production)
            # Add event hooks for latency tracking
            event_hooks={"request": [log_request], "response": [log_response]},
        )

        if is_standalone:
            logger.info("Running in standalone mode - HTTP/2 disabled for compatibility")
        else:
            logger.info("Running in integrated mode - HTTP/2 enabled for optimal performance")

        return client

    except Exception as e:
        logger.exception(f"Failed to create HTTP client: {e}")
        raise


def cleanup_httpx_client():
    """
    Closes the global httpx client and releases its resources.
    Should be called when the application is shutting down.
    """
    global _httpx_client

    if _httpx_client is not None:
        _httpx_client.close()
        _httpx_client = None
        logger.info("Closed HTTP client")
