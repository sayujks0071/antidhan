import pandas as pd
import pytest

from packages.core.historical_data import HistoricalDataLoader


class TestHistoricalDataValidation:

    @pytest.fixture
    def loader(self):
        return HistoricalDataLoader(data_dir="tests/fixtures")

    def test_clean_data(self, loader):
        """Test that valid data is preserved"""
        data = {
            'Open': [100.0, 101.0],
            'High': [105.0, 106.0],
            'Low': [95.0, 96.0],
            'Close': [102.0, 103.0],
            'No. of contracts': [1000, 2000],
            'Open Int': [5000, 6000]
        }
        df = pd.DataFrame(data)
        validated = loader.validate_data(df, "test_file.csv")
        assert len(validated) == 2

    def test_negative_prices(self, loader):
        """Test that negative prices are filtered"""
        data = {
            'Open': [100.0, -10.0],  # Negative Open
            'High': [105.0, 105.0],
            'Low': [95.0, 95.0],
            'Close': [102.0, 102.0]
        }
        df = pd.DataFrame(data)
        validated = loader.validate_data(df, "test_file.csv")
        assert len(validated) == 1
        assert validated.iloc[0]['Open'] == 100.0

    def test_zero_prices(self, loader):
        """Test that zero prices are filtered"""
        data = {
            'Open': [100.0, 0.0],  # Zero Open
            'High': [105.0, 105.0],
            'Low': [95.0, 95.0],
            'Close': [102.0, 102.0]
        }
        df = pd.DataFrame(data)
        validated = loader.validate_data(df, "test_file.csv")
        assert len(validated) == 1

    def test_ohlc_consistency(self, loader):
        """Test OHLC consistency checks"""
        data = {
            'Open': [100.0, 100.0, 100.0],
            'High': [105.0, 90.0, 105.0],  # 2nd row: High < Open (Invalid)
            'Low': [95.0, 95.0, 110.0],   # 3rd row: Low > High (Invalid)
            'Close': [102.0, 102.0, 102.0]
        }
        df = pd.DataFrame(data)
        validated = loader.validate_data(df, "test_file.csv")
        assert len(validated) == 1
        assert validated.iloc[0]['High'] == 105.0

    def test_negative_volume(self, loader):
        """Test negative volume is filtered"""
        data = {
            'Open': [100.0, 100.0],
            'High': [105.0, 105.0],
            'Low': [95.0, 95.0],
            'Close': [102.0, 102.0],
            'No. of contracts': [100, -5]
        }
        df = pd.DataFrame(data)
        validated = loader.validate_data(df, "test_file.csv")
        assert len(validated) == 1
        assert validated.iloc[0]['No. of contracts'] == 100

    def test_nan_volume(self, loader):
        """Test NaN volume is preserved (not dropped)"""
        data = {
            'Open': [100.0],
            'High': [105.0],
            'Low': [95.0],
            'Close': [102.0],
            'No. of contracts': [None]
        }
        df = pd.DataFrame(data)
        validated = loader.validate_data(df, "test_file.csv")
        assert len(validated) == 1

    def test_negative_oi(self, loader):
        """Test negative OI is filtered"""
        data = {
            'Open': [100.0, 100.0],
            'High': [105.0, 105.0],
            'Low': [95.0, 95.0],
            'Close': [102.0, 102.0],
            'Open Int': [100, -5]
        }
        df = pd.DataFrame(data)
        validated = loader.validate_data(df, "test_file.csv")
        assert len(validated) == 1
        assert validated.iloc[0]['Open Int'] == 100

    def test_missing_columns(self, loader):
        """Test behavior when columns are missing (should not crash)"""
        data = {
            'Open': [100.0, 101.0],
            # Missing High, Low, Close
        }
        df = pd.DataFrame(data)
        # Should just return as is or process what it can
        # Our code checks `if col in df.columns` so it should be fine but consistency check needs all 4
        validated = loader.validate_data(df, "test_file.csv")
        assert len(validated) == 2
