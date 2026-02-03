"""Backtesting engine using historical data"""
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import structlog

from packages.core.config import app_config
from packages.core.historical_data import HistoricalDataLoader
from packages.core.models import Position, Signal, SignalSide, Tick
from packages.core.paper_simulator import PaperSimulator
from packages.core.risk import PortfolioRisk, RiskManager
from packages.core.strategies import Strategy
from packages.core.strategies.base import StrategyContext

logger = structlog.get_logger(__name__)


class BacktestEngine:
    """
    Backtesting engine that replays historical data through strategies.
    
    Features:
    - Historical data replay
    - Strategy signal generation
    - Paper execution simulation
    - P&L tracking
    - Performance metrics
    """

    def __init__(
        self,
        initial_capital: float = 1000000,  # 10 lakh
        data_dir: str = "docs/NSE OPINONS DATA"
    ):
        self.initial_capital = initial_capital
        self.data_loader = HistoricalDataLoader(data_dir)

        # State
        self.current_capital = initial_capital
        self.positions: List[Position] = []
        self.closed_trades: List[Dict] = []
        self.signals_generated: List[Signal] = []

        # Simulators
        self.paper_sim = PaperSimulator(
            slippage_bps=app_config.risk.slippage_bps,
            fees_per_order=app_config.risk.fees_per_order
        )

        self.risk_manager = RiskManager(app_config.risk)

        # Performance tracking
        self.daily_pnl: Dict[datetime, float] = {}
        self.max_drawdown = 0.0
        self.peak_capital = initial_capital

    def run_backtest(
        self,
        strategies: List[Strategy],
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        strikes: Optional[List[float]] = None
    ) -> Dict:
        """
        Run backtest on historical data.
        
        Args:
            strategies: List of strategies to test
            symbol: NIFTY or BANKNIFTY
            start_date: Backtest start date
            end_date: Backtest end date
            strikes: Specific strikes to test (None for ATM)
        
        Returns:
            Backtest results dictionary
        """
        logger.info(
            "Starting backtest",
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital
        )

        # Get date range
        current_date = start_date

        # Get strikes if not provided
        fixed_strikes = strikes is not None
        if strikes is None:
            # Initial strikes for logging
            strikes = self.data_loader.get_atm_strikes(symbol, start_date, num_strikes=5)

        logger.info(f"Testing {len(strikes)} strikes: {strikes}")

        # Iterate through dates
        while current_date <= end_date:
            # Skip weekends (simplified - in production, check actual trading days)
            if current_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                current_date += timedelta(days=1)
                continue

            # Update strikes if not fixed
            current_strikes = strikes
            if not fixed_strikes:
                current_strikes = self.data_loader.get_atm_strikes(symbol, current_date, num_strikes=5)
                # If no strikes found for today (e.g. holiday or missing data), skip or use previous?
                if not current_strikes:
                    logger.debug(f"No strikes found for {current_date}, skipping")
                    current_date += timedelta(days=1)
                    continue

            # Process day
            self._process_day(strategies, symbol, current_date, current_strikes)

            # Move to next day
            current_date += timedelta(days=1)

        # Calculate final metrics
        results = self._calculate_results()

        logger.info(
            "Backtest completed",
            total_trades=len(self.closed_trades),
            final_capital=results['final_capital'],
            total_return=results['total_return_pct']
        )

        return results

    def _process_day(
        self,
        strategies: List[Strategy],
        symbol: str,
        date: datetime,
        strikes: List[float]
    ):
        """Process a single trading day"""
        logger.debug(f"Processing {date.strftime('%Y-%m-%d')}")

        # Get options chain for the day
        try:
            chain = self.data_loader.get_options_chain(symbol, date)
        except Exception as e:
            logger.warning(f"Failed to load data for {date}: {e}")
            return

        if chain.empty:
            logger.debug(f"Chain empty for {date}")
            return

        # Get underlying value
        underlying_value = chain['Underlying Value'].iloc[0] if 'Underlying Value' in chain.columns else None

        # Process each strike
        for strike in strikes:
            # Process both CE and PE
            for option_type in ['CE', 'PE']:
                option_data = chain[(chain['Strike Price'] == strike) & (chain['Option type'] == option_type)]

                if option_data.empty:
                    continue

                # Pre-calculate instrument and token once per day/strike/type
                # to avoid repeated hashing and Pydantic validation in the inner loop
                from packages.core.models import Instrument, InstrumentType

                inst_type = InstrumentType.CE if option_type == 'CE' else InstrumentType.PE

                # Stable deterministic token generation
                token_str = f"{symbol}_{strike}_{option_type}"
                # Use MD5 to get consistent hash across runs/platforms
                token_hash = hashlib.md5(token_str.encode()).hexdigest()
                token = int(token_hash[:8], 16)  # Take first 8 chars (32 bits)

                instrument = Instrument(
                    token=token,
                    symbol=symbol,
                    tradingsymbol=f"{symbol}{int(strike)}{option_type}",
                    exchange="NFO",
                    instrument_type=inst_type,
                    strike=strike,
                    lot_size=50 if symbol == "NIFTY" else 25,
                    tick_size=0.05
                )

                # Convert to bars
                bars = self.data_loader.convert_to_bars(option_data, symbol, strike, option_type)

                # Sort bars by timestamp to enable sequential processing
                bars.sort(key=lambda b: b.timestamp)

                # Ensure bar tokens match instrument token (vectorized assign if possible, but bars is list)
                for b in bars:
                    b.token = token

                # Pre-calculate instrument and token to avoid overhead in inner loop
                from packages.core.models import Instrument, InstrumentType
                inst_type = InstrumentType.CE if option_type == 'CE' else InstrumentType.PE

                # Stable deterministic token generation
                token_str = f"{symbol}_{strike}_{option_type}"
                # Use MD5 to get consistent hash across runs/platforms
                token_hash = hashlib.md5(token_str.encode()).hexdigest()
                token = int(token_hash[:8], 16)  # Take first 8 chars (32 bits)

                # Ensure bar tokens match instrument token (O(N) operation done once)
                for b in bars:
                    b.token = token

                instrument = Instrument(
                    token=token,
                    symbol=symbol,
                    tradingsymbol=f"{symbol}{int(strike)}{option_type}",
                    exchange="NFO",
                    instrument_type=inst_type,
                    strike=strike,
                    lot_size=50 if symbol == "NIFTY" else 25,
                    tick_size=0.05
                )

                # Generate signals
                for strategy in strategies:
                    if not strategy.enabled:
                        continue

                    # Iterate through bars to simulate intraday flow
                    for i in range(len(bars)):
                        bar = bars[i]
                        # Create tick from bar for strategy context
                        current_tick = Tick(
                            token=token,
                            timestamp=bar.timestamp,
                            last_price=bar.close,
                            last_quantity=bar.volume,
                            volume=bar.volume,
                            bid=0.0, ask=0.0, bid_quantity=0, ask_quantity=0,
                            open=bar.open, high=bar.high, low=bar.low, close=bar.close,
                            oi=bar.oi or 0, oi_day_high=0, oi_day_low=0
                        )

                        # Pass history up to this point
                        # Optimization: Pass full history or just enough window
                        # We pass slice up to current bar (inclusive)
                        history_bars = bars[:i+1]

                        signals = self._generate_signals(
                            strategy,
                            instrument,
                            bar.timestamp,
                            history_bars,
                            current_tick,
                            underlying_value
                        )

                        # Execute signals
                        for signal in signals:
                            self._execute_signal(signal, bar.timestamp)

        # Update existing positions
        self._update_positions(date, chain)

        # Check exits
        self._check_exits(date)

        # Update daily P&L
        self._update_daily_pnl(date)

    def _generate_signals(
        self,
        strategy: Strategy,
        instrument: "Instrument",
        date: datetime,
        bars: List,
        tick: Optional,
        underlying_value: float
    ) -> List[Signal]:
        """Generate signals from a strategy"""
        # Create strategy context
        context = StrategyContext(
            timestamp=date,
            instrument=instrument,
            latest_tick=tick,
            bars_5s=bars[-20:] if len(bars) >= 20 else bars,  # Last 20 bars
            bars_1s=bars[-60:] if len(bars) >= 60 else bars,  # Last 60 for 1s
            net_liquid=self.current_capital,
            available_margin=self.current_capital * 0.8,
            open_positions=len([p for p in self.positions if p.is_open]),
            underlying_price=underlying_value
        )

        # Generate signals
        try:
            signals = strategy.generate_signals(context)
            self.signals_generated.extend(signals)
            return signals
        except Exception as e:
            logger.warning(f"Strategy {strategy.name} failed: {e}")
            return []

    def _execute_signal(self, signal: Signal, date: datetime):
        """Execute a trading signal"""
        # Check risk
        portfolio_risk = self._get_portfolio_risk()

        risk_check = self.risk_manager.check_signal(signal, portfolio_risk)

        if not risk_check.approved:
            logger.debug(f"Signal rejected: {risk_check.reasons}")
            return

        # Simulate order
        quantity = risk_check.position_size

        order = self.paper_sim.simulate_order(
            instrument_token=signal.instrument.token,
            instrument_symbol=signal.instrument.tradingsymbol,
            side="BUY" if signal.side == SignalSide.LONG else "SELL",
            quantity=quantity,
            order_type="MARKET",
            current_market_price=signal.entry_price
        )

        # Open position
        position = self.paper_sim.open_position(
            signal.instrument,
            order,
            signal.side,
            signal.stop_loss,
            signal.take_profit_1,
            signal.take_profit_2
        )

        # Update risk amount
        position.risk_amount = signal.stop_distance * quantity

        self.positions.append(position)

        logger.info(
            f"Position opened: {signal.instrument.tradingsymbol}",
            side=signal.side.value,
            quantity=quantity,
            entry_price=order.average_price
        )

    def _update_positions(self, date: datetime, chain: pd.DataFrame):
        """Update position P&L with current market prices"""
        for position in self.positions:
            if not position.is_open:
                continue

            # Find current price from chain
            strike = position.instrument.strike
            option_type = 'CE' if position.instrument.instrument_type.value == 'CE' else 'PE'

            row = chain[
                (chain['Strike Price'] == strike) &
                (chain['Option type'] == option_type)
            ]

            if not row.empty:
                current_price = row.iloc[0]['LTP'] if pd.notna(row.iloc[0]['LTP']) else row.iloc[0]['Close']
                position.current_price = current_price
                position.update_pnl()

    def _check_exits(self, date: datetime):
        """Check exit conditions for positions"""
        from packages.core.exits import ExitManager

        exit_manager = ExitManager(app_config.exits)

        # Create market data dict (simplified)
        market_data = {}
        for position in self.positions:
            if position.is_open:
                # Get current tick/bar (simplified)
                # Create a mock tick from current position price
                from packages.core.models import Tick
                tick = Tick(
                    token=position.instrument.token,
                    timestamp=date,
                    last_price=position.current_price,
                    volume=0,
                    open=position.current_price,
                    high=position.current_price,
                    low=position.current_price,
                    close=position.current_price
                )
                bars = []
                market_data[position.instrument.token] = (tick, bars)

        # Check exits
        exit_signals = exit_manager.check_exits(
            self.positions,
            market_data,
            date,
            self._get_daily_pnl_pct(),
            self.current_capital
        )

        # Execute exits
        for exit_signal in exit_signals:
            position = next(
                (p for p in self.positions if p.position_id == exit_signal.position_id),
                None
            )

            if position and position.is_open:
                # Close position
                exit_order = self.paper_sim.close_position(
                    position,
                    position.current_price,
                    exit_signal.reason.value
                )

                # Record trade
                trade = {
                    "entry_date": position.entry_time,
                    "exit_date": date,
                    "symbol": position.instrument.tradingsymbol,
                    "side": position.side.value,
                    "quantity": position.quantity,
                    "entry_price": position.entry_price,
                    "exit_price": exit_order.average_price,
                    "pnl": position.realized_pnl or 0.0,
                    "exit_reason": exit_signal.reason.value
                }

                self.closed_trades.append(trade)

                # Update capital
                self.current_capital += position.realized_pnl or 0.0

    def _get_portfolio_risk(self) -> PortfolioRisk:
        """Get current portfolio risk state"""
        total_risk = sum([p.risk_amount for p in self.positions if p.is_open])
        unrealized_pnl = sum([p.unrealized_pnl for p in self.positions if p.is_open])

        return PortfolioRisk(
            net_liquid=self.current_capital,
            used_margin=total_risk * 0.5,  # Simplified
            available_margin=self.current_capital * 0.8,
            open_positions=[p for p in self.positions if p.is_open],
            total_risk_amount=total_risk,
            unrealized_pnl=unrealized_pnl,
            realized_pnl_today=sum([t.get('pnl', 0) for t in self.closed_trades]),
            daily_pnl=unrealized_pnl + sum([t.get('pnl', 0) for t in self.closed_trades]),
            daily_loss_limit=-self.initial_capital * 0.025,
            max_portfolio_heat=self.initial_capital * 0.02
        )

    def _update_daily_pnl(self, date: datetime):
        """Update daily P&L tracking"""
        realized = sum([t.get('pnl', 0) for t in self.closed_trades])
        unrealized = sum([p.unrealized_pnl for p in self.positions if p.is_open])

        self.daily_pnl[date] = realized + unrealized

        # Update drawdown
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital

        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

    def _get_daily_pnl_pct(self) -> float:
        """Get daily P&L as percentage"""
        if self.initial_capital > 0:
            return ((self.current_capital - self.initial_capital) / self.initial_capital) * 100
        return 0.0

    def _calculate_results(self) -> Dict:
        """Calculate backtest performance metrics"""
        total_return = self.current_capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100

        wins = [t for t in self.closed_trades if t.get('pnl', 0) > 0]
        losses = [t for t in self.closed_trades if t.get('pnl', 0) <= 0]

        win_rate = (len(wins) / len(self.closed_trades) * 100) if self.closed_trades else 0.0

        avg_win = sum([t['pnl'] for t in wins]) / len(wins) if wins else 0.0
        avg_loss = sum([t['pnl'] for t in losses]) / len(losses) if losses else 0.0

        profit_factor = abs(sum([t['pnl'] for t in wins]) / sum([t['pnl'] for t in losses])) if losses and sum([t['pnl'] for t in losses]) != 0 else 0.0

        return {
            "initial_capital": self.initial_capital,
            "final_capital": self.current_capital,
            "total_return": total_return,
            "total_return_pct": total_return_pct,
            "max_drawdown_pct": self.max_drawdown * 100,
            "total_trades": len(self.closed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "largest_win": max([t['pnl'] for t in wins]) if wins else 0.0,
            "largest_loss": min([t['pnl'] for t in losses]) if losses else 0.0,
            "signals_generated": len(self.signals_generated),
            "daily_pnl": self.daily_pnl
        }
