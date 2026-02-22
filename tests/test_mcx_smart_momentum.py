import sys
import os
import unittest
import pandas as pd
import numpy as np
import importlib.util

# Add project root to sys.path so we can import 'openalgo'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestMCXSmartMomentum(unittest.TestCase):
    def setUp(self):
        # Path to the strategy file
        self.strategy_path = os.path.join(os.path.dirname(__file__), '..', 'openalgo', 'strategies', 'scripts', 'mcx_crudeoil_smart_momentum.py')

    def test_file_exists(self):
        self.assertTrue(os.path.exists(self.strategy_path))

    def test_import_and_generate_signal(self):
        # Import the module dynamically
        spec = importlib.util.spec_from_file_location("mcx_crudeoil_smart_momentum", self.strategy_path)
        mcx_strat = importlib.util.module_from_spec(spec)
        sys.modules["mcx_crudeoil_smart_momentum"] = mcx_strat
        try:
            spec.loader.exec_module(mcx_strat)
        except ImportError as e:
            self.fail(f"Failed to import strategy: {e}")
        except Exception as e:
            self.fail(f"Failed to execute strategy module: {e}")

        # Check if generate_signal exists
        self.assertTrue(hasattr(mcx_strat, 'generate_signal'))

        # Test generate_signal with dummy data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='15min')
        data = {
            'timestamp': dates,
            'open': np.random.rand(100) * 100 + 6000,
            'high': np.random.rand(100) * 100 + 6050,
            'low': np.random.rand(100) * 100 + 5950,
            'close': np.random.rand(100) * 100 + 6000,
            'volume': np.random.randint(100, 1000, 100)
        }
        df = pd.DataFrame(data)

        # Run generate_signal
        try:
            signal, confidence, metadata = mcx_strat.generate_signal(df)
            print(f"Signal Generated: {signal}, Confidence: {confidence}")
            self.assertIn(signal, ["BUY", "SELL", "HOLD"])
            self.assertIsInstance(confidence, float)
            self.assertIsInstance(metadata, dict)
        except Exception as e:
            self.fail(f"generate_signal raised exception: {e}")

if __name__ == '__main__':
    unittest.main()
