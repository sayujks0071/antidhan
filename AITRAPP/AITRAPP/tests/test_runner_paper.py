import asyncio
import os
import sys
import unittest
from datetime import datetime

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from packages.core.runner import Runner


class TestRunnerPaper(unittest.TestCase):
    def test_paper_local_fills(self):
        """Test B — Paper runner processes ticks and updates position"""

        runner = Runner("paper-local", "ORB", "NIFTY", data_dir="tests/fixtures")

        # Let's rewrite the test to use `unittest.mock` to verifying interactions
        from unittest.mock import MagicMock, patch

        with patch('packages.core.runner.PaperSimulator') as MockSim:
            # Setup mock
            mock_sim_instance = MockSim.return_value
            mock_order = MagicMock()
            mock_order.average_price = 100.0
            mock_order.side = "BUY"
            mock_order.quantity = 50
            mock_sim_instance.simulate_order.return_value = mock_order

            mock_pos = MagicMock()
            mock_pos.is_open = True
            mock_pos.unrealized_pnl = 100.0
            mock_pos.realized_pnl = 0.0
            mock_sim_instance.open_position.return_value = mock_pos

            # Also need to mock strategies to ensure they return a signal
            mock_strategy = MagicMock()
            mock_signal = MagicMock()
            mock_signal.side = "LONG" # Enums might be needed
            # Mock the StrategyContext and Signal
            from packages.core.models import Instrument, InstrumentType, Signal, SignalSide

            inst = Instrument(
                token=1, symbol="NIFTY", tradingsymbol="NIFTY25000CE",
                exchange="NFO", instrument_type=InstrumentType.CE,
                strike=25000, lot_size=50, tick_size=0.05
            )

            sig = Signal(
                timestamp=datetime.now(),
                instrument=inst,
                side=SignalSide.LONG,
                entry_price=100,
                stop_loss=90,
                take_profit_1=110,
                take_profit_2=120,
                strategy_name="TEST"
            )

            mock_strategy.generate_signals.return_value = [sig]
            runner.strategies = [mock_strategy]

            # Run the coroutine
            with patch('asyncio.sleep', return_value=None):
                asyncio.run(runner.run_paper_local(minutes=0.001))

            # Assertions
            # 1. Did we check signals?
            mock_strategy.generate_signals.assert_called()

            # 2. Did we simulate an order?
            mock_sim_instance.simulate_order.assert_called()

            # 3. Did we open a position?
            mock_sim_instance.open_position.assert_called()

if __name__ == '__main__':
    unittest.main()
