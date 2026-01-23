import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from packages.core.backtest import BacktestEngine
from packages.core.strategies.base import Strategy
from packages.core.models import Signal, SignalSide, Instrument, InstrumentType, Bar, Tick

class MockStrategy(Strategy):
    def __init__(self, name="MockStrategy", params=None):
        super().__init__(name, params or {})
        self.signal_count = 0
        self.last_bar_timestamp = None

    def generate_signals(self, context):
        # Verify sequential processing
        if self.last_bar_timestamp:
            assert context.timestamp > self.last_bar_timestamp

        self.last_bar_timestamp = context.timestamp
        self.signal_count += 1

        # Verify token propagation
        assert context.instrument.token > 0
        assert context.latest_tick.token == context.instrument.token

        # Verify history accumulation
        # context.bars_5s is actually bars_1s (1 min) in backtest usually
        # but let's just check length increases
        assert len(context.bars_5s) > 0

        # Generate a dummy signal on the 5th bar
        if self.signal_count == 5:
            return [Signal(
                strategy_name=self.name,
                timestamp=context.timestamp,
                instrument=context.instrument,
                side=SignalSide.LONG,
                entry_price=100.0,
                stop_loss=90.0,
                take_profit_1=110.0,
                take_profit_2=120.0,
                confidence=1.0,
                rationale="Test"
            )]
        return []

@pytest.fixture
def mock_data_loader():
    with patch('packages.core.backtest.HistoricalDataLoader') as MockLoader:
        loader_instance = MockLoader.return_value

        # Mock options chain
        import pandas as pd
        chain_df = pd.DataFrame({
            'Strike Price': [10000],
            'Option type': ['CE'],
            'Underlying Value': [9900],
            'LTP': [100],
            'Close': [100]
        })
        loader_instance.get_options_chain.return_value = chain_df
        loader_instance.get_atm_strikes.return_value = [10000]

        # Mock bars
        bars = []
        for i in range(10):
            ts = datetime(2025, 1, 1, 9, 15 + i)
            bars.append(Bar(
                token=0, # Will be overwritten
                timestamp=ts,
                open=100, high=105, low=95, close=100,
                volume=100, oi=500
            ))
        loader_instance.convert_to_bars.return_value = bars

        yield loader_instance

def test_backtest_sequential_processing(mock_data_loader):
    engine = BacktestEngine(data_dir="dummy")
    # Inject mock loader
    engine.data_loader = mock_data_loader

    strategy = MockStrategy()

    engine.run_backtest(
        strategies=[strategy],
        symbol="NIFTY",
        start_date=datetime(2025, 1, 1),
        end_date=datetime(2025, 1, 1),
        strikes=[10000]
    )

    # Assertions
    assert strategy.signal_count == 10
    assert len(engine.signals_generated) >= 1
    assert len(engine.positions) >= 1
