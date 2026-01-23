import os
import unittest
from unittest.mock import patch, MagicMock
from src.auth.kite_auth import KiteAuth
from kiteconnect import KiteConnect, exceptions

class TestKiteAuthUnit(unittest.TestCase):

    @patch.dict(os.environ, {"KITE_API_KEY": "test_key", "KITE_API_SECRET": "test_secret"})
    @patch("src.auth.kite_auth.KiteConnect")
    def test_exchange_request_token(self, MockKiteConnect):
        # Setup mock
        mock_kite = MockKiteConnect.return_value
        mock_kite.generate_session.return_value = {
            "access_token": "new_access_token",
            "user_id": "user123"
        }

        # Init auth
        auth = KiteAuth()

        # Call method
        with patch("src.auth.kite_auth.dotenv.set_key") as mock_set_key:
             token = auth.exchange_request_token("test_req_token")

             # Verify
             assert token == "new_access_token"
             assert auth.access_token == "new_access_token"

             # Verify KiteConnect called correctly
             mock_kite.generate_session.assert_called_with("test_req_token", api_secret="test_secret")
             mock_kite.set_access_token.assert_called_with("new_access_token")

    @patch.dict(os.environ, {"KITE_API_KEY": "test_key", "KITE_API_SECRET": "test_secret"})
    @patch("src.auth.kite_auth.KiteConnect")
    def test_is_session_valid_true(self, MockKiteConnect):
        mock_kite = MockKiteConnect.return_value
        # profile returns normally
        mock_kite.profile.return_value = {}

        auth = KiteAuth()
        auth.access_token = "valid_token"

        assert auth.is_session_valid() is True

    @patch.dict(os.environ, {"KITE_API_KEY": "test_key", "KITE_API_SECRET": "test_secret"})
    @patch("src.auth.kite_auth.KiteConnect")
    def test_is_session_valid_false(self, MockKiteConnect):
        mock_kite = MockKiteConnect.return_value
        # profile raises TokenException
        mock_kite.profile.side_effect = exceptions.TokenException("Token expired")

        auth = KiteAuth()
        auth.access_token = "invalid_token"

        assert auth.is_session_valid() is False

    @patch.dict(os.environ, {"KITE_API_KEY": "test_key", "KITE_API_SECRET": "test_secret"})
    @patch("src.auth.kite_auth.KiteConnect")
    def test_get_login_url(self, MockKiteConnect):
        mock_kite = MockKiteConnect.return_value
        mock_kite.login_url.return_value = "http://login-url"

        auth = KiteAuth()
        assert auth.get_login_url() == "http://login-url"

if __name__ == '__main__':
    unittest.main()
