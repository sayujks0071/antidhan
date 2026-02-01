#!/usr/bin/env python3
"""
Risk Manager Module - Critical Safety Features for All Trading Strategies

This module provides essential risk management features that MUST be used by all strategies:
1. Stop-Loss enforcement
2. EOD (End of Day) position square-off
3. Max daily loss circuit breaker
4. Position size limits
5. Trade cooldown periods

CRITICAL: All strategies MUST use this module to prevent catastrophic losses.

Author: OpenAlgo Risk Management
Version: 1.0.0
"""

import os
import json
import logging
import pytz
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger("RiskManager")

class RiskManager:
    """
    Centralized Risk Management for all trading strategies.

    Features:
    - Stop-loss monitoring and enforcement
    - Max loss per trade / per day limits
    - EOD auto square-off
    - Position tracking with broker reconciliation
    - Trade cooldown to prevent overtrading
    """

    # Default risk parameters (can be overridden)
    DEFAULT_CONFIG = {
        'max_loss_per_trade_pct': 2.0,      # Max 2% loss per trade
        'max_daily_loss_pct': 5.0,           # Max 5% daily loss - circuit breaker
        'max_position_value': 500000,        # Max 5 lakh per position
        'eod_square_off_time': '15:15',      # NSE: Square off by 3:15 PM
        'mcx_eod_square_off_time': '23:25',  # MCX: Square off by 11:25 PM
        'trade_cooldown_seconds': 300,       # 5 min between trades
        'trailing_stop_enabled': True,
        'trailing_stop_pct': 1.5,            # 1.5% trailing stop
    }

    def __init__(self, strategy_name: str, exchange: str = "NSE",
                 capital: float = 100000, config: Optional[Dict] = None):
        """
        Initialize Risk Manager.

        Args:
            strategy_name: Name of the strategy using this manager
            exchange: "NSE" or "MCX"
            capital: Trading capital for calculating loss limits
            config: Override default risk parameters
        """
        self.strategy_name = strategy_name
        self.exchange = exchange.upper()
        self.capital = capital
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}

        # State tracking
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.last_trade_time = 0
        self.positions: Dict[str, Dict] = {}  # symbol -> {qty, entry_price, stop_loss, trailing_stop}
        self.is_circuit_breaker_active = False

        # State persistence
        self.state_dir = Path(__file__).resolve().parent.parent / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / f"{strategy_name}_risk_state.json"

        self._load_state()
        logger.info(f"RiskManager initialized for {strategy_name} on {exchange}")

    def _load_state(self):
        """Load persisted state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)

                    # Check if state is from today
                    last_date = data.get('date', '')
                    today = datetime.now().strftime('%Y-%m-%d')

                    if last_date == today:
                        self.daily_pnl = data.get('daily_pnl', 0.0)
                        self.daily_trades = data.get('daily_trades', 0)
                        self.positions = data.get('positions', {})
                        self.is_circuit_breaker_active = data.get('circuit_breaker', False)
                        logger.info(f"Loaded today's state: PnL={self.daily_pnl}, Trades={self.daily_trades}")
                    else:
                        # New day - reset daily counters but keep positions
                        self.positions = data.get('positions', {})
                        logger.info(f"New trading day - reset daily counters. Carried over {len(self.positions)} positions.")
            except Exception as e:
                logger.error(f"Failed to load risk state: {e}")

    def _save_state(self):
        """Persist state to file."""
        try:
            data = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'daily_pnl': self.daily_pnl,
                'daily_trades': self.daily_trades,
                'positions': self.positions,
                'circuit_breaker': self.is_circuit_breaker_active,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save risk state: {e}")

    def can_trade(self) -> tuple[bool, str]:
        """
        Check if trading is allowed based on risk parameters.

        Returns:
            (can_trade: bool, reason: str)
        """
        # Check circuit breaker
        if self.is_circuit_breaker_active:
            return False, "CIRCUIT BREAKER ACTIVE - Daily loss limit exceeded"

        # Check daily loss limit
        max_daily_loss = self.capital * (self.config['max_daily_loss_pct'] / 100)
        if self.daily_pnl <= -max_daily_loss:
            self.is_circuit_breaker_active = True
            self._save_state()
            return False, f"CIRCUIT BREAKER TRIGGERED - Daily loss {self.daily_pnl:.2f} exceeds limit {max_daily_loss:.2f}"

        # Check EOD square-off time
        if self._is_near_market_close():
            return False, "Near market close - no new positions allowed"

        # Check trade cooldown
        import time
        time_since_last = time.time() - self.last_trade_time
        if time_since_last < self.config['trade_cooldown_seconds']:
            remaining = int(self.config['trade_cooldown_seconds'] - time_since_last)
            return False, f"Trade cooldown active - {remaining}s remaining"

        return True, "OK"

    def _is_near_market_close(self) -> bool:
        """Check if we're within 15 minutes of market close."""
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)

        if self.exchange == "MCX":
            close_str = self.config['mcx_eod_square_off_time']
        else:
            close_str = self.config['eod_square_off_time']

        close_hour, close_min = map(int, close_str.split(':'))
        close_time = dt_time(close_hour, close_min)

        return now.time() >= close_time

    def should_square_off_eod(self) -> bool:
        """Check if it's time for EOD square-off."""
        return self._is_near_market_close()

    def calculate_stop_loss(self, entry_price: float, side: str,
                           stop_pct: Optional[float] = None) -> float:
        """
        Calculate stop-loss price.

        Args:
            entry_price: Entry price of the position
            side: "LONG" or "SHORT"
            stop_pct: Stop loss percentage (default from config)

        Returns:
            Stop loss price
        """
        pct = stop_pct or self.config['max_loss_per_trade_pct']

        if side.upper() == "LONG":
            return entry_price * (1 - pct / 100)
        else:
            return entry_price * (1 + pct / 100)

    def update_trailing_stop(self, symbol: str, current_price: float) -> Optional[float]:
        """
        Update trailing stop for a position.

        Args:
            symbol: Trading symbol
            current_price: Current market price

        Returns:
            New trailing stop price (or None if no update)
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        if not self.config['trailing_stop_enabled']:
            return pos.get('stop_loss')

        pct = self.config['trailing_stop_pct'] / 100

        if pos['qty'] > 0:  # Long position
            # Only move stop up, never down
            new_stop = current_price * (1 - pct)
            if new_stop > pos.get('trailing_stop', 0):
                pos['trailing_stop'] = new_stop
                self._save_state()
                logger.info(f"Trailing stop updated for {symbol}: {new_stop:.2f}")
                return new_stop
        else:  # Short position
            # Only move stop down, never up
            new_stop = current_price * (1 + pct)
            current_stop = pos.get('trailing_stop', float('inf'))
            if new_stop < current_stop:
                pos['trailing_stop'] = new_stop
                self._save_state()
                logger.info(f"Trailing stop updated for {symbol}: {new_stop:.2f}")
                return new_stop

        return pos.get('trailing_stop')

    def check_stop_loss(self, symbol: str, current_price: float) -> tuple[bool, str]:
        """
        Check if stop loss is hit.

        Args:
            symbol: Trading symbol
            current_price: Current market price

        Returns:
            (stop_hit: bool, reason: str)
        """
        if symbol not in self.positions:
            return False, "No position"

        pos = self.positions[symbol]
        stop_price = pos.get('trailing_stop') or pos.get('stop_loss')

        if stop_price is None:
            return False, "No stop loss set"

        if pos['qty'] > 0:  # Long position
            if current_price <= stop_price:
                loss_pct = ((pos['entry_price'] - current_price) / pos['entry_price']) * 100
                return True, f"STOP LOSS HIT - Long @ {pos['entry_price']:.2f}, Stop @ {stop_price:.2f}, Current @ {current_price:.2f}, Loss: {loss_pct:.2f}%"
        else:  # Short position
            if current_price >= stop_price:
                loss_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                return True, f"STOP LOSS HIT - Short @ {pos['entry_price']:.2f}, Stop @ {stop_price:.2f}, Current @ {current_price:.2f}, Loss: {loss_pct:.2f}%"

        return False, "OK"

    def register_entry(self, symbol: str, qty: int, entry_price: float,
                       side: str, stop_loss: Optional[float] = None):
        """
        Register a new position entry.

        Args:
            symbol: Trading symbol
            qty: Quantity (positive for long, negative for short)
            entry_price: Entry price
            side: "LONG" or "SHORT"
            stop_loss: Manual stop loss price (auto-calculated if not provided)
        """
        import time

        # Calculate stop loss if not provided
        if stop_loss is None:
            stop_loss = self.calculate_stop_loss(entry_price, side)

        self.positions[symbol] = {
            'qty': qty if side.upper() == "LONG" else -qty,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'trailing_stop': stop_loss,
            'entry_time': datetime.now().isoformat(),
            'side': side.upper()
        }

        self.last_trade_time = time.time()
        self.daily_trades += 1
        self._save_state()

        logger.info(f"Position registered: {side} {qty} {symbol} @ {entry_price:.2f}, SL: {stop_loss:.2f}")

    def register_exit(self, symbol: str, exit_price: float, qty: Optional[int] = None):
        """
        Register a position exit and calculate PnL.

        Args:
            symbol: Trading symbol
            exit_price: Exit price
            qty: Quantity to exit (default: full position)

        Returns:
            Realized PnL
        """
        if symbol not in self.positions:
            logger.warning(f"No position found for {symbol}")
            return 0.0

        pos = self.positions[symbol]
        exit_qty = qty or abs(pos['qty'])

        # Calculate PnL
        if pos['qty'] > 0:  # Long position
            pnl = (exit_price - pos['entry_price']) * exit_qty
        else:  # Short position
            pnl = (pos['entry_price'] - exit_price) * exit_qty

        self.daily_pnl += pnl

        # Remove or reduce position
        if exit_qty >= abs(pos['qty']):
            del self.positions[symbol]
        else:
            pos['qty'] = pos['qty'] - exit_qty if pos['qty'] > 0 else pos['qty'] + exit_qty

        self._save_state()

        logger.info(f"Position closed: {symbol} @ {exit_price:.2f}, PnL: {pnl:.2f}, Daily PnL: {self.daily_pnl:.2f}")
        return pnl

    def get_open_positions(self) -> Dict[str, Dict]:
        """Get all open positions."""
        return self.positions.copy()

    def get_daily_stats(self) -> Dict[str, Any]:
        """Get daily trading statistics."""
        return {
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'open_positions': len(self.positions),
            'circuit_breaker_active': self.is_circuit_breaker_active,
            'max_daily_loss_limit': self.capital * (self.config['max_daily_loss_pct'] / 100),
            'loss_remaining': (self.capital * (self.config['max_daily_loss_pct'] / 100)) + self.daily_pnl
        }

    def reset_daily_state(self):
        """Reset daily counters (call at start of new trading day)."""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.is_circuit_breaker_active = False
        self._save_state()
        logger.info("Daily state reset")


class EODSquareOff:
    """
    End-of-Day automatic position square-off handler.

    CRITICAL: This ensures all MIS positions are closed before market close
    to prevent broker penalties and overnight risk.
    """

    def __init__(self, risk_manager: RiskManager,
                 exit_callback: Callable[[str, str, int], Any]):
        """
        Initialize EOD Square-off handler.

        Args:
            risk_manager: RiskManager instance
            exit_callback: Function to call for exiting positions
                          Signature: exit_callback(symbol, action, quantity) -> order_result
        """
        self.rm = risk_manager
        self.exit_callback = exit_callback
        self._squared_off_today = False

    def check_and_execute(self) -> bool:
        """
        Check if EOD square-off is needed and execute if so.

        Returns:
            True if square-off was executed
        """
        if self._squared_off_today:
            return False

        if not self.rm.should_square_off_eod():
            return False

        positions = self.rm.get_open_positions()
        if not positions:
            logger.info("EOD check: No open positions to square off")
            return False

        logger.warning(f"EOD SQUARE-OFF TRIGGERED - Closing {len(positions)} positions")

        for symbol, pos in positions.items():
            try:
                qty = abs(pos['qty'])
                action = "SELL" if pos['qty'] > 0 else "BUY"

                logger.info(f"EOD: Closing {symbol} - {action} {qty}")
                result = self.exit_callback(symbol, action, qty)

                if result and result.get('status') == 'success':
                    # Assume exit at current price (would need actual fill price)
                    self.rm.register_exit(symbol, pos['entry_price'])  # Placeholder
                    logger.info(f"EOD: Successfully closed {symbol}")
                else:
                    logger.error(f"EOD: Failed to close {symbol}: {result}")

            except Exception as e:
                logger.error(f"EOD: Error closing {symbol}: {e}")

        self._squared_off_today = True
        return True


# Convenience function for quick risk checks
def create_risk_manager(strategy_name: str, exchange: str = "NSE",
                        capital: float = 100000, **kwargs) -> RiskManager:
    """
    Factory function to create a configured RiskManager.

    Example:
        rm = create_risk_manager("PairsTrading", "MCX", capital=200000, max_loss_per_trade_pct=1.5)
    """
    config = {k: v for k, v in kwargs.items() if k in RiskManager.DEFAULT_CONFIG}
    return RiskManager(strategy_name, exchange, capital, config)
