import threading
import time
import requests
import os
import pytest
from unittest.mock import patch, MagicMock
from scripts import kite_auth_bootstrap
from scripts.kite_auth_bootstrap import main, start_server

class TestKiteAuthIntegration:

    @pytest.fixture
    def mock_env(self):
        with patch.dict(os.environ, {
            "KITE_API_KEY": "test_key",
            "KITE_API_SECRET": "test_secret",
            "APP_MODE": "PAPER"
        }):
            yield

    @pytest.fixture
    def mock_kite_auth(self):
        # Use autospec=True to ensure we are mocking actual methods that exist
        with patch("scripts.kite_auth_bootstrap.KiteAuth", autospec=True) as MockKiteAuth:
            instance = MockKiteAuth.return_value
            instance.is_session_valid.return_value = False
            instance.get_login_url.return_value = "http://mock-login-url"
            instance.exchange_request_token.return_value = "new_access_token"
            instance.access_token = "mock_initial_token"
            yield instance

    @pytest.fixture(autouse=True)
    def reset_captured_token(self):
        # Reset the global variable before each test
        kite_auth_bootstrap.captured_request_token = None
        yield
        kite_auth_bootstrap.captured_request_token = None

    def test_bootstrap_script_valid_session(self, mock_env):
        """Test that script exits 0 if session is already valid"""
        with patch("scripts.kite_auth_bootstrap.KiteAuth", autospec=True) as MockKiteAuth:
            instance = MockKiteAuth.return_value
            instance.is_session_valid.return_value = True
            instance.access_token = "mock_initial_token"

            # Patch sys.argv to prevent argparse from seeing pytest args
            with patch("sys.argv", ["script_name"]):
                with pytest.raises(SystemExit) as pytest_wrapped_e:
                    main()
                assert pytest_wrapped_e.type == SystemExit
                assert pytest_wrapped_e.value.code == 0

    def test_bootstrap_script_check_only_fails(self, mock_env, mock_kite_auth):
        """Test that --check-only exits 1 if session is invalid"""
        with patch("sys.argv", ["script", "--check-only"]):
            with pytest.raises(SystemExit) as pytest_wrapped_e:
                main()
            assert pytest_wrapped_e.type == SystemExit
            assert pytest_wrapped_e.value.code == 1

    def test_callback_server_flow(self, mock_env, mock_kite_auth):
        """
        Integration test simulating the full flow:
        1. Script starts server (in thread)
        2. We simulate a browser request to the callback URL
        3. Script should capture token, exchange it, and exit 0
        """
        port = 8090
        # Start server in a thread
        server_thread = threading.Thread(target=start_server, args=(port,))
        server_thread.daemon = True
        server_thread.start()

        # Give server a moment to start
        time.sleep(1)

        try:
            # Simulate callback
            callback_url = f"http://localhost:{port}/?request_token=test_req_token"
            response = requests.get(callback_url)

            assert response.status_code == 200
            assert "Authentication Captured" in response.text

            # Now verify that the global variable in the script module was updated
            assert kite_auth_bootstrap.captured_request_token == "test_req_token"

        finally:
            pass

    def test_bootstrap_end_to_end_mocked(self, mock_env, mock_kite_auth):
        """
        Simulate main() but mock start_server to just set the token immediately
        to avoid actual network calls or threading issues in unit tests.
        """
        # We simulate the effect of the server running by setting the global variable
        kite_auth_bootstrap.captured_request_token = "mocked_captured_token"

        with patch("sys.argv", ["script", "--port", "8000"]), \
             patch("scripts.kite_auth_bootstrap.start_server") as mock_start, \
             patch("scripts.kite_auth_bootstrap.threading.Thread") as MockThread:

            mock_thread_instance = MockThread.return_value
            mock_thread_instance.join.return_value = None

            with pytest.raises(SystemExit) as pytest_wrapped_e:
                main()

            assert pytest_wrapped_e.type == SystemExit
            assert pytest_wrapped_e.value.code == 0

            mock_kite_auth.exchange_request_token.assert_called_with("mocked_captured_token")
            mock_kite_auth.persist_access_token.assert_called_with("new_access_token")

    def test_bootstrap_trading_mode_override(self, mock_kite_auth):
        """Test that TRADING_MODE env var correctly sets APP_MODE"""
        with patch.dict(os.environ, {"TRADING_MODE": "live"}):
             # Ensure APP_MODE is unset to verify override
             if "APP_MODE" in os.environ:
                 del os.environ["APP_MODE"]

             with patch("sys.argv", ["script", "--check-only"]):
                with pytest.raises(SystemExit):
                    main()

                assert os.environ["APP_MODE"] == "LIVE"

    def test_bootstrap_trading_mode_paper(self, mock_kite_auth):
        """Test that TRADING_MODE env var correctly sets APP_MODE to PAPER"""
        with patch.dict(os.environ, {"TRADING_MODE": "paper"}):
             if "APP_MODE" in os.environ:
                 del os.environ["APP_MODE"]

             with patch("sys.argv", ["script", "--check-only"]):
                with pytest.raises(SystemExit):
                    main()

                assert os.environ["APP_MODE"] == "PAPER"
