
import time
import httpx
from unittest.mock import patch, MagicMock
from openalgo.utils.httpx_client import request

def test_retry_after_header_respected():
    """
    Test that the Retry-After header is respected if present in 429/503 responses.
    """
    url = "http://example.com/api"

    # Mock response with Retry-After header
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "2"} # 2 seconds
    mock_response.request = MagicMock()
    mock_response.http_version = "HTTP/1.1"

    # Mock successful response for the second attempt
    success_response = MagicMock(spec=httpx.Response)
    success_response.status_code = 200
    success_response.http_version = "HTTP/1.1"

    with patch("openalgo.utils.httpx_client.get_httpx_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # side_effect: first call returns 429, second returns 200
        mock_client.request.side_effect = [mock_response, success_response]

        start_time = time.time()

        # We expect this to sleep for at least 2 seconds because of Retry-After
        # If it uses backoff_factor=0.5, 2**0 = 1 -> 0.5s sleep (fail)
        request("GET", url, max_retries=1, backoff_factor=0.1)

        end_time = time.time()
        duration = end_time - start_time

        print(f"Request took {duration:.2f} seconds")

        # If it respected Retry-After, duration should be >= 2.0
        # If it used backoff, it would be around 0.1s
        if duration >= 2.0:
            print("PASS: Retry-After header was respected.")
        else:
            print("FAIL: Retry-After header was IGNORED.")

if __name__ == "__main__":
    test_retry_after_header_respected()
