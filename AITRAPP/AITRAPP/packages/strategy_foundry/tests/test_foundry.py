import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from packages.strategy_foundry.data.loader import DataLoader
from packages.strategy_foundry.factory.generator import StrategyGenerator
from packages.strategy_foundry.backtest.engine import BacktestEngine
from packages.strategy_foundry.adapters.core_costs import CostModel

@pytest.fixture
def mock_df():
    dates = pd.date_range(start="2023-01-01", periods=100, freq="5min")
    df = pd.DataFrame({
        "datetime": dates,
        "open": np.random.rand(100) * 10 + 100,
        "high": np.random.rand(100) * 10 + 105,
        "low": np.random.rand(100) * 10 + 95,
        "close": np.random.rand(100) * 10 + 100,
        "volume": np.random.randint(100, 1000, 100)
    })
    return df

def test_loader_structure():
    loader = DataLoader()
    assert loader.cache_dir is not None

def test_strategy_generation(mock_df):
    gen = StrategyGenerator()
    cand = gen.generate_candidate()
    assert cand.strategy_id is not None
    assert len(cand.entry_rules) > 0

    # Generate signal
    sig = gen.generate_signal(mock_df, cand)
    assert len(sig) == len(mock_df)
    assert sig.isin([0, 1]).all()

def test_backtest_engine(mock_df):
    gen = StrategyGenerator()
    cand = gen.generate_candidate()

    cost_model = CostModel(slippage_bps=1, brokerage_per_order=1, tax_bps=1, spread_guard_bps=1)
    engine = BacktestEngine(cost_model)

    trades = engine.run(mock_df, cand)
    assert isinstance(trades, pd.DataFrame)
    if not trades.empty:
        assert 'net_return' in trades.columns
        assert 'entry_idx' in trades.columns

def test_grammar_coverage():
    gen = StrategyGenerator()
    # Generate 20 candidates to cover different blocks
    for _ in range(20):
        c = gen.generate_candidate()
        assert c.max_bars_hold > 0
        assert c.stop_loss_atr > 0
