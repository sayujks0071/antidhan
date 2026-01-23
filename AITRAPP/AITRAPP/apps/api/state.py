"""Application state management"""

import asyncio
from contextlib import suppress
import logging
from collections import defaultdict
from datetime import datetime, time
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import uuid4

import pytz
from kiteconnect import KiteConnect

from packages.core.config import AppConfig, Settings
from packages.core.execution import ExecutionEngine, OrderResult
from packages.core.exits import ExitManager, ExitSignal
from packages.core.instruments import InstrumentManager
from packages.core.market_data import MarketDataStream
from packages.core.config import AppMode
from packages.core.models import (
    Bar,
    PortfolioState,
    Position,
    PositionStatus,
    RankedOpportunity,
    Signal,
    SignalSide,
    SystemState,
    Tick,
)
from packages.core.ranker import SignalRanker
from packages.core.risk import PortfolioRisk, RiskManager
from packages.core.strategies import (
    ORBStrategy,
    OptionsRankerStrategy,
    TrendPullbackStrategy,
)
from packages.core.strategies.base import Strategy, StrategyContext

logger = logging.getLogger(__name__)

DEFAULT_CAPITAL_BASE = Decimal("1000000")


class AppState:
    """Central application state that orchestrates the trading loop"""

    def __init__(self, settings: Settings, config: AppConfig):
        self.settings = settings
        self.config = config

        # Mode & flags
        self.mode = AppMode(config.mode)
        self.is_paused = False
        self._is_running = False
        self._main_loop_task: Optional[asyncio.Task] = None

        # Capital tracking
        risk_capital = getattr(config.risk, "capital_base", None)
        self.capital_base = Decimal(str(risk_capital)) if risk_capital else DEFAULT_CAPITAL_BASE
        self.realized_pnl_today = Decimal("0")
        self.pending_signals = 0
        self.trades_today = 0
        self.wins_today = 0
        self.losses_today = 0

        # Broker session
        self.kite = KiteConnect(api_key=settings.kite_api_key)
        self.kite.set_access_token(settings.kite_access_token)

        # Market infrastructure
        self.instrument_manager = InstrumentManager(self.kite, config.universe, settings)
        # Backwards compat for existing callers
        self.instrument_service = self.instrument_manager
        self.universe_builder = self.instrument_manager

        self.market_data_stream: Optional[MarketDataStream] = None
        self.market_data_cache: Dict[int, Dict[int, List[Bar]]] = defaultdict(dict)

        # Core engines
        self.strategies: List[Strategy] = self._initialize_strategies()
        self.ranking_engine = SignalRanker(config.ranking)
        self.risk_manager = RiskManager(config.risk)
        self.execution_engine = ExecutionEngine(self.kite, config.execution, settings)
        self.exit_manager = ExitManager(config.exits)

        # Positions & universe
        self.positions: Dict[str, Position] = {}
        self.universe_tokens: List[int] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _initialize_strategies(self) -> List[Strategy]:
        strategies: List[Strategy] = []
        for strategy_config in self.config.strategies:
            params = strategy_config.params
            if strategy_config.name == "ORB":
                strategies.append(ORBStrategy(strategy_config.name, params))
            elif strategy_config.name == "TrendPullback":
                strategies.append(TrendPullbackStrategy(strategy_config.name, params))
            elif strategy_config.name == "OptionsRanker":
                strategies.append(OptionsRankerStrategy(strategy_config.name, params))
        logger.info("Initialized strategies", count=len(strategies))
        return strategies

    async def startup(self) -> None:
        logger.info("Running startup sequence…")
        await self.instrument_manager.sync_instruments()
        await self.instrument_manager.sync_fo_ban_list()
        self.universe_tokens = await self.instrument_manager.build_universe()

        self.market_data_stream = MarketDataStream(
            settings=self.settings,
            window_seconds=[1, 5],
            on_bar_callback=self._on_bar_update,
        )
        self.market_data_stream.initialize()
        self.market_data_stream.start()
        await self._subscribe_to_universe()

        self._is_running = True
        self._main_loop_task = asyncio.create_task(self._main_loop())
        logger.info("✅ Startup complete")

    async def shutdown(self) -> None:
        logger.info("Running shutdown sequence…")
        self._is_running = False
        if self._main_loop_task:
            self._main_loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._main_loop_task

        if self.market_data_stream:
            self.market_data_stream.stop()

        logger.info("✅ Shutdown complete")

    async def _subscribe_to_universe(self) -> None:
        if not self.market_data_stream or not self.universe_tokens:
            return
        subscribe_mode = getattr(self.config, "websocket", {}).get("subscribe_mode", "full")
        attempts = 0
        while not self.market_data_stream.is_connected and attempts < 20:
            await asyncio.sleep(0.5)
            attempts += 1
        self.market_data_stream.subscribe(self.universe_tokens, mode=subscribe_mode.lower())
        logger.info("Subscribed to universe", instruments=len(self.universe_tokens))

    async def _on_bar_update(self, token: int, window_sec: int, bars: List[Bar]) -> None:
        if not bars:
            return
        # Store a shallow copy to avoid mutation from aggregator
        self.market_data_cache[token][window_sec] = list(bars)

    async def _main_loop(self) -> None:
        logger.info("Main loop started")
        while self._is_running:
            try:
                await self._trading_cycle()
            except Exception as exc:  # pragma: no cover - defensive log
                logger.exception("Error in main loop", error=str(exc))
            await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # Trading cycle
    # ------------------------------------------------------------------
    async def _trading_cycle(self) -> None:
        if self.is_paused or not self.market_data_stream:
            return

        now = datetime.now(pytz.UTC)
        if self._should_force_flat(now):
            logger.warning("EOD square-off triggered - closing all positions")
            await self.close_all_positions(reason="EOD")
            return

        market_snapshot = self._build_market_snapshot()
        if not market_snapshot:
            logger.debug("Market data snapshot not ready yet")
            return

        portfolio_risk = self._update_portfolio_risk()
        contexts = self._build_strategy_contexts(market_snapshot, portfolio_risk)
        if not contexts:
            logger.debug("No strategy contexts available")
            await self._evaluate_position_exits(market_snapshot, portfolio_risk, now)
            return

        signals = self._generate_signals(contexts)
        if not signals:
            await self._evaluate_position_exits(market_snapshot, portfolio_risk, now)
            return

        opportunities = self.ranking_engine.rank_signals(signals, market_snapshot)
        if opportunities:
            await self._execute_ranked_opportunities(opportunities, portfolio_risk)

        await self._evaluate_position_exits(market_snapshot, portfolio_risk, now)

    def _build_market_snapshot(self) -> Dict[int, tuple[Tick, List[Bar]]]:
        if not self.market_data_stream:
            return {}
        snapshot: Dict[int, tuple[Tick, List[Bar]]] = {}
        for token, window_map in self.market_data_cache.items():
            bars_5s = window_map.get(5)
            if not bars_5s or len(bars_5s) < 5:
                continue
            tick = self.market_data_stream.get_latest_tick(token)
            if not tick:
                continue
            snapshot[token] = (tick, bars_5s)
        return snapshot

    def _build_strategy_contexts(
        self,
        market_snapshot: Dict[int, tuple[Tick, List[Bar]]],
        portfolio_risk: PortfolioRisk,
    ) -> Dict[int, StrategyContext]:
        contexts: Dict[int, StrategyContext] = {}
        open_positions = len([pos for pos in self.positions.values() if pos.is_open])
        for token, (tick, bars_5s) in market_snapshot.items():
            instrument = self.instrument_manager.get_instrument(token)
            if not instrument:
                continue
            bars_1s = self.market_data_cache.get(token, {}).get(1, [])
            context = StrategyContext(
                timestamp=datetime.now(pytz.UTC),
                instrument=instrument,
                latest_tick=tick,
                bars_1s=bars_1s,
                bars_5s=bars_5s,
                net_liquid=portfolio_risk.net_liquid,
                available_margin=portfolio_risk.available_margin,
                open_positions=open_positions,
            )
            contexts[token] = context
        return contexts

    def _generate_signals(self, contexts: Dict[int, StrategyContext]) -> List[Signal]:
        signals: List[Signal] = []
        for strategy in self.strategies:
            if not strategy.enabled:
                continue
            for context in contexts.values():
                try:
                    generated = strategy.generate_signals(context)
                    if generated:
                        signals.extend(generated)
                except Exception as exc:
                    logger.exception(
                        "Strategy failed to generate signals",
                        strategy=strategy.name,
                        error=str(exc)
                    )
        self.pending_signals = len(signals)
        return signals

    async def _execute_ranked_opportunities(
        self,
        opportunities: List[RankedOpportunity],
        portfolio_risk: PortfolioRisk,
    ) -> None:
        for opportunity in opportunities:
            signal = opportunity.signal
            risk_check = self.risk_manager.check_signal(signal, portfolio_risk)
            if not risk_check.approved or risk_check.position_size <= 0:
                logger.debug(
                    "Risk check failed",
                    instrument=signal.instrument.tradingsymbol,
                    reasons=risk_check.reasons,
                )
                continue

            result, entry_order = await self.execution_engine.execute_signal(
                signal,
                risk_check.position_size,
            )
            if result != OrderResult.SUCCESS or not entry_order:
                logger.warning(
                    "Signal execution failed",
                    strategy=signal.strategy_name,
                    instrument=signal.instrument.tradingsymbol,
                    result=result.name,
                )
                continue

            self._record_new_position(signal, entry_order, risk_check.position_size)

            trade_risk = signal.stop_distance * risk_check.position_size
            portfolio_risk.total_risk_amount += trade_risk
            estimated_margin = self.risk_manager.estimate_margin_required(
                signal.instrument,
                risk_check.position_size,
                signal.entry_price,
            )
            portfolio_risk.used_margin += estimated_margin
            portfolio_risk.available_margin = max(
                0.0,
                portfolio_risk.net_liquid - portfolio_risk.used_margin,
            )

    def _record_new_position(self, signal: Signal, entry_order, quantity: int) -> None:
        position_id = f"{uuid4()}"
        fill_price = entry_order.average_price or signal.entry_price
        position = Position(
            position_id=position_id,
            instrument=signal.instrument,
            entry_time=entry_order.timestamp,
            entry_price=fill_price,
            quantity=quantity,
            side=signal.side,
            current_price=fill_price,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_2=signal.take_profit_2,
            risk_amount=signal.stop_distance * quantity,
            strategy_name=signal.strategy_name,
            entry_order_id=entry_order.order_id,
        )
        self.positions[position_id] = position
        strategy = self._get_strategy(signal.strategy_name)
        if strategy:
            strategy.on_position_opened()
        logger.info(
            "Position opened",
            position_id=position_id,
            symbol=signal.instrument.tradingsymbol,
            qty=quantity,
        )

    async def _evaluate_position_exits(
        self,
        market_snapshot: Dict[int, tuple[Tick, List[Bar]]],
        portfolio_risk: PortfolioRisk,
        current_time: datetime,
    ) -> None:
        open_positions = [pos for pos in self.positions.values() if pos.is_open]
        if not open_positions:
            return

        for position in open_positions:
            tick = market_snapshot.get(position.instrument.token)
            if tick:
                position.current_price = tick[0].last_price
                position.update_pnl()

        exit_signals = self.exit_manager.check_exits(
            positions=open_positions,
            market_data=market_snapshot,
            current_time=current_time,
            daily_pnl_pct=portfolio_risk.daily_pnl_pct,
            net_liquid=portfolio_risk.net_liquid,
        )
        if exit_signals:
            await self._handle_exit_signals(exit_signals)

    async def _handle_exit_signals(self, exit_signals: List[ExitSignal]) -> None:
        for exit_signal in exit_signals:
            position = self.positions.get(exit_signal.position_id)
            if not position or not position.is_open:
                continue
            order = await self.execution_engine.close_position(
                position,
                reason=exit_signal.reason.value,
            )
            if order:
                self._finalize_position(position, order.average_price)
                self.exit_manager.on_position_closed(position.position_id)

    # ------------------------------------------------------------------
    # Public controls
    # ------------------------------------------------------------------
    async def pause_trading(self) -> None:
        logger.warning("🛑 Trading paused")
        self.is_paused = True

    async def resume_trading(self) -> None:
        logger.info("▶️ Trading resumed")
        self.is_paused = False

    async def kill_switch(self) -> Dict[str, int | str]:
        logger.critical("🚨 KILL SWITCH ACTIVATED")
        await self.pause_trading()
        cancelled_orders = await self._cancel_all_pending_orders()
        closed_positions = await self.close_all_positions(reason="KILL_SWITCH")
        return {
            "cancelled_orders": cancelled_orders,
            "closed_positions": closed_positions,
            "status": "FLATTENED",
        }

    async def close_all_positions(self, reason: str = "MANUAL") -> int:
        closed = 0
        for position in list(self.positions.values()):
            if not position.is_open:
                continue
            order = await self.execution_engine.close_position(position, reason=reason)
            if order:
                self._finalize_position(position, order.average_price)
                self.exit_manager.on_position_closed(position.position_id)
                closed += 1
        return closed

    def get_system_state(self) -> SystemState:
        portfolio_state = self._build_portfolio_state()
        active_orders = len([
            order for order in self.execution_engine.orders.values() if order.is_active
        ])
        return SystemState(
            timestamp=datetime.now(pytz.UTC),
            mode=self.mode.value,
            is_paused=self.is_paused,
            is_market_open=self._is_market_open(),
            portfolio=portfolio_state,
            pending_signals=self.pending_signals,
            active_orders=active_orders,
            trades_today=self.trades_today,
            wins_today=self.wins_today,
            losses_today=self.losses_today,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _update_portfolio_risk(self) -> PortfolioRisk:
        return self.risk_manager.update_portfolio_risk(
            net_liquid=float(self.capital_base),
            positions=list(self.positions.values()),
            realized_pnl_today=float(self.realized_pnl_today),
        )

    def _build_portfolio_state(self) -> PortfolioState:
        portfolio_risk = self._update_portfolio_risk()
        return PortfolioState(
            timestamp=datetime.now(pytz.UTC),
            net_liquid=portfolio_risk.net_liquid,
            used_margin=portfolio_risk.used_margin,
            available_margin=portfolio_risk.available_margin,
            open_positions=[pos for pos in self.positions.values() if pos.is_open],
            total_positions=len(self.positions),
            unrealized_pnl=portfolio_risk.unrealized_pnl,
            realized_pnl_today=portfolio_risk.realized_pnl_today,
            daily_pnl=portfolio_risk.daily_pnl,
            daily_pnl_pct=portfolio_risk.daily_pnl_pct,
            portfolio_heat=portfolio_risk.total_risk_amount,
            portfolio_heat_pct=portfolio_risk.portfolio_heat_pct,
            max_portfolio_heat_pct=self.config.risk.max_portfolio_heat_pct,
            daily_loss_limit=portfolio_risk.daily_loss_limit,
        )

    async def _cancel_all_pending_orders(self) -> int:
        count = 0
        for order in list(self.execution_engine.orders.values()):
            if order.is_active:
                if await self.execution_engine.cancel_order(order.client_order_id):
                    count += 1
        return count

    def _finalize_position(self, position: Position, exit_price: float) -> None:
        position.status = PositionStatus.CLOSED
        position.close_time = datetime.now(pytz.UTC)
        position.close_price = exit_price
        if position.side == SignalSide.LONG:
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity
        position.realized_pnl = pnl
        self.realized_pnl_today += Decimal(str(pnl))
        self.trades_today += 1
        if pnl > 0:
            self.wins_today += 1
        else:
            self.losses_today += 1
        strategy = self._get_strategy(position.strategy_name)
        if strategy:
            strategy.on_position_closed(pnl)
        logger.info(
            "Position closed",
            position_id=position.position_id,
            pnl=pnl,
        )

    def _get_strategy(self, name: str) -> Optional[Strategy]:
        for strategy in self.strategies:
            if strategy.name == name:
                return strategy
        return None

    def _should_force_flat(self, current_time: datetime) -> bool:
        market_cfg = getattr(self.config, "market", None)
        if not market_cfg or not getattr(market_cfg, "eod_squareoff_enabled", True):
            return False
        cutoff_str = getattr(market_cfg, "eod_squareoff_time", "15:25")
        cutoff_hour, cutoff_minute = map(int, cutoff_str.split(":"))
        ist = pytz.timezone(self.config.timezone)
        now_ist = current_time.astimezone(ist)
        return now_ist.time() >= time(cutoff_hour, cutoff_minute)

    def _is_market_open(self) -> bool:
        market_cfg = getattr(self.config, "market", None)
        ist = pytz.timezone(self.config.timezone)
        now_ist = datetime.now(ist)
        if now_ist.weekday() >= 5:
            return False
        open_str = getattr(market_cfg, "open_time", "09:15")
        close_str = getattr(market_cfg, "close_time", "15:30")
        open_hour, open_minute = map(int, open_str.split(":"))
        close_hour, close_minute = map(int, close_str.split(":"))
        market_open = now_ist.replace(hour=open_hour, minute=open_minute, second=0, microsecond=0)
        market_close = now_ist.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)
        return market_open <= now_ist <= market_close
