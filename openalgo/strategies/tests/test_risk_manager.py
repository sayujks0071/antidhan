import unittest
import os
import shutil
import json
from datetime import datetime, timedelta, time
from pathlib import Path
from unittest.mock import patch, MagicMock

from openalgo.strategies.utils.risk_manager import RiskManager, EODSquareOff, create_risk_manager

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.strategy_name = "TestStrategy"
        self.exchange = "NSE"
        self.capital = 100000
        self.rm = RiskManager(self.strategy_name, self.exchange, self.capital)

        # Ensure clean state start
        if self.rm.state_file.exists():
            os.remove(self.rm.state_file)
        self.rm._load_state()

    def tearDown(self):
        # Clean up state file
        if self.rm.state_file.exists():
            os.remove(self.rm.state_file)

    def test_initialization(self):
        self.assertEqual(self.rm.daily_pnl, 0.0)
        self.assertEqual(self.rm.daily_trades, 0)
        self.assertEqual(len(self.rm.positions), 0)
        self.assertFalse(self.rm.is_circuit_breaker_active)

    def test_calculate_stop_loss(self):
        # Long position: 100 - 2% = 98
        sl_long = self.rm.calculate_stop_loss(100, "LONG")
        self.assertEqual(sl_long, 98.0)

        # Short position: 100 + 2% = 102
        sl_short = self.rm.calculate_stop_loss(100, "SHORT")
        self.assertEqual(sl_short, 102.0)

    def test_register_entry_and_exit(self):
        symbol = "TESTSYM"
        qty = 10
        price = 100.0

        # Entry
        self.rm.register_entry(symbol, qty, price, "LONG")
        self.assertIn(symbol, self.rm.positions)
        self.assertEqual(self.rm.positions[symbol]['qty'], 10)
        self.assertEqual(self.rm.daily_trades, 1)

        # Check persisted state
        with open(self.rm.state_file, 'r') as f:
            data = json.load(f)
            self.assertIn(symbol, data['positions'])

        # Exit with profit
        exit_price = 105.0
        pnl = self.rm.register_exit(symbol, exit_price)
        self.assertEqual(pnl, 50.0) # (105-100)*10
        self.assertNotIn(symbol, self.rm.positions)
        self.assertEqual(self.rm.daily_pnl, 50.0)

    def test_stop_loss_check(self):
        symbol = "TESTSL"
        self.rm.register_entry(symbol, 10, 100.0, "LONG")
        # SL should be 98.0

        # Price above SL
        hit, reason = self.rm.check_stop_loss(symbol, 99.0)
        self.assertFalse(hit)

        # Price at SL
        hit, reason = self.rm.check_stop_loss(symbol, 98.0)
        self.assertTrue(hit)
        self.assertIn("STOP LOSS HIT", reason)

        # Price below SL
        hit, reason = self.rm.check_stop_loss(symbol, 97.0)
        self.assertTrue(hit)

    def test_trailing_stop(self):
        symbol = "TESTTRAIL"
        self.rm.register_entry(symbol, 10, 100.0, "LONG")
        # Initial SL = 98.0 (2% default)
        # Trailing pct = 1.5%

        # Price moves up to 110. New SL should be 110 * (1 - 0.015) = 108.35
        new_sl = self.rm.update_trailing_stop(symbol, 110.0)
        self.assertAlmostEqual(new_sl, 108.35)

        # Check stored position
        pos = self.rm.positions[symbol]
        self.assertAlmostEqual(pos['trailing_stop'], 108.35)

        # Price drops to 109. SL should NOT move down.
        new_sl_2 = self.rm.update_trailing_stop(symbol, 109.0)
        self.assertAlmostEqual(new_sl_2, 108.35)

    def test_circuit_breaker(self):
        # Max daily loss is 5% of 100000 = 5000

        # Simulate a loss of 6000
        self.rm.daily_pnl = -6000.0

        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("CIRCUIT BREAKER TRIGGERED", reason)
        self.assertTrue(self.rm.is_circuit_breaker_active)

        # Subsequent checks should fail immediately
        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("CIRCUIT BREAKER ACTIVE", reason)

    @patch('openalgo.strategies.utils.risk_manager.datetime')
    def test_trade_cooldown(self, mock_datetime):
        # Set time to 10:00 AM which is safe
        mock_now = datetime(2023, 10, 27, 10, 0, 0)
        mock_datetime.now.return_value = mock_now

        self.rm.config['trade_cooldown_seconds'] = 1

        # First trade
        self.rm.register_entry("S1", 1, 100, "LONG")

        # Immediate next trade attempt
        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("Trade cooldown active", reason)

        # Wait for cooldown
        import time
        time.sleep(1.1)

        can_trade, reason = self.rm.can_trade()
        self.assertTrue(can_trade)

    @patch('openalgo.strategies.utils.risk_manager.datetime')
    def test_eod_square_off(self, mock_datetime):
        # Mock time to be 15:20 (past 15:15)
        mock_now = datetime(2023, 10, 27, 15, 20)
        mock_datetime.now.return_value = mock_now

        self.assertTrue(self.rm.should_square_off_eod())

        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("Near market close", reason)

class TestEODSquareOff(unittest.TestCase):
    def setUp(self):
        self.rm = RiskManager("TestEOD", "NSE", 100000)
        # Add a position
        self.rm.register_entry("POS1", 10, 100, "LONG")

        self.mock_exit = MagicMock()
        self.mock_exit.return_value = {'status': 'success'}
        self.eod = EODSquareOff(self.rm, self.mock_exit)

    def tearDown(self):
        if self.rm.state_file.exists():
            os.remove(self.rm.state_file)

    @patch('openalgo.strategies.utils.risk_manager.datetime')
    def test_execute_square_off(self, mock_datetime):
        # Mock time to be past square off
        mock_now = datetime(2023, 10, 27, 15, 20)
        mock_datetime.now.return_value = mock_now

        executed = self.eod.check_and_execute()
        self.assertTrue(executed)

        # Verify exit callback was called
        self.mock_exit.assert_called_with("POS1", "SELL", 10)

        # Verify position is closed in RM
        self.assertEqual(len(self.rm.positions), 0)

        # Should not execute again
        executed_again = self.eod.check_and_execute()
        self.assertFalse(executed_again)

if __name__ == '__main__':
    unittest.main()
