import pytest
import sys
import importlib.util
from unittest.mock import MagicMock, patch
import os

# Helper to import the strategy
def import_strategy():
    script_path = os.path.join(os.getcwd(), "openalgo/strategies/scripts/vbt_ranking_strategy.py")
    spec = importlib.util.spec_from_file_location("vbt_ranking_strategy", script_path)
    strategy_module = importlib.util.module_from_spec(spec)
    sys.modules["vbt_ranking_strategy"] = strategy_module
    spec.loader.exec_module(strategy_module)
    return strategy_module

@pytest.fixture
def strategy():
    return import_strategy()

def test_run_strategy_premium(strategy):
    with patch('vectorbt.YFData.download') as mock_download, \
         patch('vectorbt.MA.run') as mock_ma, \
         patch('vectorbt.Portfolio.from_signals') as mock_pf_cls:

        # Mock YFData download
        mock_data = MagicMock()
        mock_download.return_value = mock_data
        mock_price = MagicMock()
        mock_data.get.return_value = mock_price
        # Ensure price is not empty (mock shape)
        mock_price.shape = [100]

        # Mock MA
        mock_ma_instance = MagicMock()
        mock_ma.return_value = mock_ma_instance
        mock_ma_instance.ma_crossed_above.return_value = MagicMock()
        mock_ma_instance.ma_crossed_below.return_value = MagicMock()

        # Mock Portfolio
        mock_pf = MagicMock()
        mock_pf_cls.return_value = mock_pf

        # Setup mock returns for Premium rank
        mock_pf.total_return.return_value = 0.60 # 60%
        mock_pf.sharpe_ratio.return_value = 1.6 # > 1.5

        result = strategy.run_strategy("BTC-USD")

        assert result["Rank"] == "Premium"
        assert result["Total Return [%]"] == 60.0
        assert result["Sharpe Ratio"] == 1.6

def test_run_strategy_moderate(strategy):
    with patch('vectorbt.YFData.download') as mock_download, \
         patch('vectorbt.MA.run') as mock_ma, \
         patch('vectorbt.Portfolio.from_signals') as mock_pf_cls:

        mock_data = MagicMock()
        mock_download.return_value = mock_data
        mock_price = MagicMock()
        mock_data.get.return_value = mock_price
        mock_price.shape = [100]

        mock_ma_instance = MagicMock()
        mock_ma.return_value = mock_ma_instance
        mock_ma_instance.ma_crossed_above.return_value = MagicMock()
        mock_ma_instance.ma_crossed_below.return_value = MagicMock()

        mock_pf = MagicMock()
        mock_pf_cls.return_value = mock_pf

        # Setup mock returns for Moderate rank
        mock_pf.total_return.return_value = 0.20 # 20%
        mock_pf.sharpe_ratio.return_value = 1.0 # > 0.8

        result = strategy.run_strategy("BTC-USD")

        assert result["Rank"] == "Moderate"

def test_run_strategy_low(strategy):
    with patch('vectorbt.YFData.download') as mock_download, \
         patch('vectorbt.MA.run') as mock_ma, \
         patch('vectorbt.Portfolio.from_signals') as mock_pf_cls:

        mock_data = MagicMock()
        mock_download.return_value = mock_data
        mock_price = MagicMock()
        mock_data.get.return_value = mock_price
        mock_price.shape = [100]

        mock_ma_instance = MagicMock()
        mock_ma.return_value = mock_ma_instance
        mock_ma_instance.ma_crossed_above.return_value = MagicMock()
        mock_ma_instance.ma_crossed_below.return_value = MagicMock()

        mock_pf = MagicMock()
        mock_pf_cls.return_value = mock_pf

        # Setup mock returns for Low rank
        mock_pf.total_return.return_value = -0.10 # -10%
        mock_pf.sharpe_ratio.return_value = 0.5

        result = strategy.run_strategy("BTC-USD")

        assert result["Rank"] == "Low"

def test_ticker_kwargs_passed(strategy):
    with patch('vectorbt.YFData.download') as mock_download, \
         patch('vectorbt.MA.run') as mock_ma, \
         patch('vectorbt.Portfolio.from_signals') as mock_pf_cls:

        mock_data = MagicMock()
        mock_download.return_value = mock_data
        mock_price = MagicMock()
        mock_data.get.return_value = mock_price
        mock_price.shape = [100]

        mock_ma_instance = MagicMock()
        mock_ma.return_value = mock_ma_instance
        mock_ma_instance.ma_crossed_above.return_value = MagicMock()
        mock_ma_instance.ma_crossed_below.return_value = MagicMock()

        mock_pf = MagicMock()
        mock_pf_cls.return_value = mock_pf
        mock_pf.total_return.return_value = 0.0
        mock_pf.sharpe_ratio.return_value = 0.0

        strategy.run_strategy("BTC-USD")

        # Verify ticker_kwargs was passed
        args, kwargs = mock_download.call_args
        assert "ticker_kwargs" in kwargs
        assert kwargs["ticker_kwargs"] == {}
