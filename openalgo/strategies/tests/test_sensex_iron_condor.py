import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add strategies dir to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set env vars for config
os.environ['OPENALGO_APIKEY'] = 'test_key'
os.environ['STRATEGY_NAME'] = 'test_sensex_ic'
os.environ['UNDERLYING'] = 'SENSEX'

# Mock requests to avoid network calls during import/init
with patch('requests.Session') as mock_session:
    # Import the strategy module
    import sensex_iron_condor

class TestSensexIronCondor(unittest.TestCase):
    @patch('sensex_iron_condor.OptionChainClient')
    @patch('sensex_iron_condor.APIClient')
    def test_init(self, MockAPIClient, MockOptionChainClient):
        # Test instantiation
        strategy = sensex_iron_condor.SensexIronCondorStrategy()
        self.assertIsNotNone(strategy)
        self.assertEqual(strategy.client, MockOptionChainClient.return_value)
        self.assertEqual(strategy.api_client, MockAPIClient.return_value)
        self.assertEqual(sensex_iron_condor.UNDERLYING_EXCHANGE, 'BSE_INDEX')
        self.assertEqual(sensex_iron_condor.OPTIONS_EXCHANGE, 'BFO')

if __name__ == '__main__':
    unittest.main()
