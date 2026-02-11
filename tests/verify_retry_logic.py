import sys
import time
import unittest
from unittest.mock import MagicMock

# Mock httpx before importing utils.httpx_client
mock_httpx = MagicMock()
sys.modules["httpx"] = mock_httpx

# Also mock openalgo_observability just in case
sys.modules["openalgo_observability"] = MagicMock()
sys.modules["openalgo_observability.logging_setup"] = MagicMock()

# Setup paths
import os
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "openalgo"))

# Now import the module to test
# We need to ensure we can import it even if previous import failed partly or something
if "utils.httpx_client" in sys.modules:
    del sys.modules["utils.httpx_client"]

from utils import httpx_client

class TestRetryLogic(unittest.TestCase):
    def test_retry_with_backoff_decorator(self):
        """Test the retry_with_backoff decorator logic independently."""

        # Mock a function that fails initially
        mock_func = MagicMock()
        mock_func.__name__ = "mock_func"  # Add name for logging
        mock_func.side_effect = [Exception("Fail 1"), Exception("Fail 2"), "Success"]

        # Decorate it
        # We need to manually apply the decorator because @syntax runs at definition time
        # but we want to decorate our mock
        wrapper = httpx_client.retry_with_backoff(max_retries=3, backoff_factor=0.01)
        decorated_func = wrapper(mock_func)

        # Run it
        print("Running decorated function...")
        result = decorated_func()

        # Verify
        self.assertEqual(result, "Success")
        self.assertEqual(mock_func.call_count, 3)
        print("✅ Retry decorator: Retried 3 times and succeeded.")

    def test_retry_with_backoff_failure(self):
        """Test the retry_with_backoff decorator when it fails completely."""

        # Mock a function that always fails
        mock_func = MagicMock()
        mock_func.__name__ = "mock_func_fail" # Add name for logging
        mock_func.side_effect = Exception("Fail Always")

        # Decorate it
        wrapper = httpx_client.retry_with_backoff(max_retries=2, backoff_factor=0.01)
        decorated_func = wrapper(mock_func)

        # Run it and expect exception
        print("Running failing function...")
        with self.assertRaises(Exception) as cm:
            decorated_func()

        self.assertEqual(str(cm.exception), "Fail Always")
        # Initial call (1) + 2 retries = 3 calls
        self.assertEqual(mock_func.call_count, 3)
        print("✅ Retry decorator failure: Retried max times and raised exception.")

if __name__ == "__main__":
    unittest.main()
