"""Main trading orchestrator - connects all components"""
import asyncio
from datetime import datetime, time
from typing import List, Optional

import structlog
from kiteconnect import KiteConnect

from packages.core.config import app_config, settings
from packages.core.execution import ExecutionEngine, OrderResult
from packages.core.exits import ExitManager
from packages.core.instruments import InstrumentManager
from packages.core.leader_lock import LeaderLock
from packages.core.market_data import MarketDataStream
from packages.core.metrics import (
    record_decision_approved,
    record_decision_rejected,
    record_order_placed,
    record_signal,
    record_signal_ranked,
    record_signals_per_cycle,
)
from packages.core.models import Position, PositionStatus, Signal, SignalSide, SystemState
from packages.core.oco import OCOManager
from packages.core.paper_simulator import PaperSimulator
from packages.core.persistence import (
    get_config_sha,
    persist_decision,
    persist_order,
    persist_signal,
)
from packages.core.ranker import SignalRanker
from packages.core.redis_bus import RedisBus
from packages.core.risk import PortfolioRisk, RiskManager
from packages.core.strategies.base import Strategy

logger = structlog.get_logger(__name__)


class TradingOrchestrator:
    """
    Main orchestrator that runs the complete trading pipeline:
    
    1. Market Data → WebSocket ticks → Bars → Indicators
    2. Strategies → Generate signals
    3. Ranker → Score and rank signals
    4. Risk Manager → Validate and size positions
    5. Execution Engine → Place orders
    6. Exit Manager → Monitor and close positions
    7. State Management → Track everything
    """

    def __init__(
        self,
        kite: KiteConnect,
        strategies: List[Strategy],
        instrument_manager: InstrumentManager,
        market_data_stream: MarketDataStream,
        risk_manager: RiskManager,
        execution_engine: ExecutionEngine,
        exit_manager: ExitManager,
        ranker: SignalRanker,
        redis_bus: Optional[RedisBus] = None,
        oco_manager: Optional[OCOManager] = None
    ):
        self.kite = kite
        self.strategies = strategies
        self.instrument_manager = instrument_manager
        self.market_data_stream = market_data_stream
        self.risk_manager = risk_manager
        self.execution_engine = execution_engine
        self.exit_manager = exit_manager
        self.ranker = ranker
        self.redis_bus = redis_bus
        self.oco_manager = oco_manager
        self.leader_lock: Optional[LeaderLock] = None

        # State
        self.positions: List[Position] = []
        self.is_running = False
        self.is_paused = False
        self._mode = settings.app_mode.value

        # Paper simulator
        self.paper_sim = PaperSimulator(
            slippage_bps=app_config.risk.slippage_bps,
            fees_per_order=app_config.risk.fees_per_order
        )

        # Scan cycle timing
        from packages.core.metrics import scan_interval_seconds
        self.scan_interval_seconds = 5  # Scan every 5 seconds
        scan_interval_seconds.set(self.scan_interval_seconds)  # Expose in metrics
        self.last_scan_time: Optional[datetime] = None

        # Scan supervisor
        self._stop = asyncio.Event()
        self._scan_task: Optional[asyncio.Task] = None

        # Performance tracking
        self.signals_generated_today = 0
        self.orders_placed_today = 0
        self.trades_completed_today = 0

    async def start(self) -> None:
        """Start the trading orchestrator"""
        logger.info("Starting Trading Orchestrator", mode=settings.app_mode.value)

        # Acquire leader lock if Redis available
        from packages.core.metrics import is_leader
        if self.redis_bus and hasattr(self.redis_bus, 'redis') and self.redis_bus.redis:
            self.leader_lock = LeaderLock(self.redis_bus.redis)
            acquired = await self.leader_lock.acquire()
            if not acquired:
                logger.critical("Failed to acquire leader lock - another instance may be running")
                raise RuntimeError("Cannot start: leader lock not acquired")

            # Set leader metric immediately
            instance_id = getattr(self.leader_lock, 'instance_id', 'default')
            is_leader.labels(instance_id=instance_id).set(1)
            logger.info("Leader lock acquired and metric set", instance_id=instance_id)

            # Start refresh task
            asyncio.create_task(self._refresh_leader_lock())

        # Re-arm OCO watchers for open positions (crash-safe recovery)
        await self._recover_open_positions()

        self.is_running = True
        self.is_paused = False

        # Start market data stream
        if not self.market_data_stream.is_connected:
            self.market_data_stream.start()
            await asyncio.sleep(2)  # Wait for connection

        # Subscribe to universe
        universe_tokens = self.instrument_manager.get_universe_tokens()
        if universe_tokens:
            self.market_data_stream.subscribe(universe_tokens[:50])  # Limit for demo
            logger.info(f"Subscribed to {len(universe_tokens[:50])} instruments")

        # Start scan supervisor (never silently dies)
        from packages.core.metrics import scan_supervisor_state
        if self._scan_task and not self._scan_task.done():
            scan_supervisor_state.set(1)  # running
            logger.info("Scan supervisor already running")
        else:
            self._stop.clear()
            scan_supervisor_state.set(1)  # running
            self._scan_task = asyncio.create_task(self._scan_supervisor(), name="scan-supervisor")
            logger.info("Scan supervisor scheduled", interval=self.scan_interval_seconds)

    async def stop(self) -> None:
        """Stop the trading orchestrator"""
        logger.info("Stopping Trading Orchestrator")

        self.is_running = False
        self.is_paused = True

        # Stop scan supervisor
        from packages.core.metrics import scan_supervisor_state
        if self._scan_task:
            scan_supervisor_state.set(4)  # stopping
            self._stop.set()
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            scan_supervisor_state.set(0)  # stopped
            logger.info("Scan supervisor stopped")

        # Release leader lock
        if self.leader_lock:
            await self.leader_lock.release()

        # Stop market data stream
        if self.market_data_stream:
            self.market_data_stream.stop()

        # Close all positions if in live mode
        if settings.app_mode.value == "LIVE" and self.positions:
            logger.warning("Closing all positions before shutdown")
            await self._close_all_positions("SHUTDOWN")

    async def _refresh_leader_lock(self) -> None:
        """
        Periodically refresh the lock. If lost:
          • set metrics
          • pause trading
          • try auto-reacquire with exponential backoff (jitter)
          • resume trading when lock is re-acquired
        """
        import random

        from packages.core.metrics import is_leader, kill_switch_total

        backoff = [1, 2, 4, 8, 15, 30]  # seconds; cap at 30s
        ttl_fraction = 10  # refresh cadence (10 seconds)

        while self.is_running:
            try:
                if not self.leader_lock:
                    await asyncio.sleep(ttl_fraction)
                    continue

                ok = await self.leader_lock.refresh()
                instance_id = getattr(self.leader_lock, 'instance_id', 'default')

                if ok:
                    is_leader.labels(instance_id=instance_id).set(1)
                    await asyncio.sleep(ttl_fraction)
                    continue

                # LOST leadership
                is_leader.labels(instance_id=instance_id).set(0)
                logger.warning("Leader lock lost — pausing orchestrator")
                await self.pause()

                # Optional: count the event for alerting
                kill_switch_total.labels(reason="leader_lock_lost").inc()

                # Log audit event
                from packages.storage.database import get_db_session
                from packages.storage.models import AuditActionEnum, AuditLog
                try:
                    with get_db_session() as db:
                        audit_log = AuditLog(
                            action=AuditActionEnum.LEADER_LOCK,
                            message="Leader lock lost - orchestrator paused",
                            details={
                                "event": "LEADER_LOCK_LOST",
                                "instance_id": instance_id,
                                "config_sha": get_config_sha()
                            }
                        )
                        db.add(audit_log)
                        db.commit()
                except Exception as e:
                    logger.warning("Failed to log leader lock loss", error=str(e))

                # Try to reacquire with backoff+jitter
                reacquired = False
                for delay in backoff:
                    if not self.is_running:
                        return
                    await asyncio.sleep(delay + random.uniform(0, 0.5))
                    try:
                        if await self.leader_lock.acquire():
                            is_leader.labels(instance_id=instance_id).set(1)
                            logger.info("Leader lock re-acquired — resuming orchestrator")

                            # Track leader change
                            from packages.core.metrics import leader_changes_total
                            leader_changes_total.inc()

                            # Resume orchestrator
                            self.is_paused = False
                            logger.info("Orchestrator resumed after leader lock re-acquisition")

                            # Log audit event
                            from packages.storage.database import get_db_session
                            from packages.storage.models import AuditActionEnum, AuditLog
                            try:
                                with get_db_session() as db:
                                    audit_log = AuditLog(
                                        action=AuditActionEnum.LEADER_LOCK,
                                        message="Leader lock re-acquired - orchestrator resumed",
                                        details={
                                            "event": "LEADER_LOCK_ACQUIRED",
                                            "instance_id": instance_id,
                                            "config_sha": get_config_sha()
                                        }
                                    )
                                    db.add(audit_log)
                                    db.commit()
                            except Exception as e:
                                logger.warning("Failed to log leader lock re-acquisition", error=str(e))

                            reacquired = True
                            break
                    except Exception as e:
                        logger.exception("Leader re-acquire attempt failed", error=str(e))

                if not reacquired:
                    # Don't kill the process; just wait and try again on next loop
                    logger.error("Unable to re-acquire leader lock after retries; staying paused")
                    await asyncio.sleep(backoff[-1])
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("Unexpected error in leader lock refresh loop", error=str(e))
                await asyncio.sleep(1)

    async def _recover_open_positions(self) -> None:
        """Recover open positions and re-arm OCO watchers (crash-safe)"""
        from packages.core.models import Position, PositionStatus, SignalSide
        from packages.storage.database import get_db_session
        from packages.storage.models import Order, OrderStatusEnum, PositionStatusEnum
        from packages.storage.models import Position as DBPosition

        with get_db_session() as db:
            open_positions = db.query(DBPosition).filter_by(
                status=PositionStatusEnum.OPEN
            ).all()

            if not open_positions:
                return

            logger.info(f"Recovering {len(open_positions)} open positions")

            for pos in open_positions:
                # Recover to memory
                instrument = self.instrument_manager.get_instrument(pos.instrument_token)
                if instrument:
                    # Map Enums
                    side_map = {
                        "LONG": SignalSide.LONG,
                        "SHORT": SignalSide.SHORT,
                        "BUY": SignalSide.LONG,
                        "SELL": SignalSide.SHORT
                    }
                    # Handle if side is enum object
                    db_side = pos.side.value if hasattr(pos.side, 'value') else pos.side
                    core_side = side_map.get(str(db_side), SignalSide.LONG)

                    # Create Core Position
                    core_pos = Position(
                        position_id=pos.position_id,
                        instrument=instrument,
                        entry_time=pos.opened_at,
                        entry_price=pos.avg_price,
                        quantity=pos.qty,
                        side=core_side,
                        current_price=pos.current_price or pos.avg_price,
                        unrealized_pnl=pos.unrealized or 0.0,
                        stop_loss=pos.stop_loss or 0.0,
                        trailing_stop=pos.trailing_stop,
                        take_profit_1=pos.take_profit_1,
                        take_profit_2=pos.take_profit_2,
                        risk_amount=pos.risk_amount or 0.0,
                        status=PositionStatus.OPEN,
                        strategy_name=pos.strategy_name or "",
                        entry_order_id=pos.entry_order_id,
                        exit_order_id=pos.exit_order_id
                    )

                    # Prevent duplicates
                    if not any(p.position_id == core_pos.position_id for p in self.positions):
                        self.positions.append(core_pos)
                        logger.info("Restored position to memory", position_id=core_pos.position_id)
                else:
                    logger.error("Failed to recover position: instrument not found",
                               token=pos.instrument_token, position_id=pos.position_id)

                if not pos.oco_group:
                    continue

                # Find PLACED children orders
                children = db.query(Order).filter_by(
                    parent_group=pos.oco_group,
                    status=OrderStatusEnum.PLACED
                ).all()

                if children:
                    logger.info(
                        "Re-arming OCO watcher for position",
                        position_id=pos.position_id,
                        oco_group=pos.oco_group,
                        children_count=len(children)
                    )
                    # OrderWatcher will pick these up automatically
                    # This ensures sibling cancel logic is armed after restart

    async def pause(self) -> None:
        """Pause trading (stop new entries, keep positions)"""
        logger.warning("🛑 Trading PAUSED")
        self.is_paused = True

    async def resume(self) -> None:
        """Resume trading"""
        logger.info("▶️  Trading RESUMED")
        self.is_paused = False

    def set_mode(self, mode: str) -> None:
        """Set trading mode (PAPER/LIVE)"""
        self._mode = mode
        logger.info(f"Mode set to {mode}")

    async def on_entry_filled(self, fill_event: dict) -> None:
        """Called by OrderWatcher when an ENTRY order is filled"""
        client_order_id = fill_event.get("client_order_id")
        if not client_order_id:
            return

        logger.info("Entry order filled", client_order_id=client_order_id)

        # Update order status in DB
        from packages.core.persistence import update_order_status
        from packages.storage.models import OrderSideEnum, OrderStatusEnum, SideEnum
        order_model = update_order_status(
            client_order_id=client_order_id,
            broker_order_id=fill_event.get("broker_order_id"),
            status=OrderStatusEnum.FILLED,
            filled_qty=fill_event.get("filled_qty"),
            average_price=fill_event.get("average_price")
        )

        if not order_model or not order_model.decision_id:
            return

        # Get decision to find signal
        from packages.storage.database import get_db_session
        from packages.storage.models import Decision, PositionStatusEnum
        from packages.storage.models import Position as DBPosition
        with get_db_session() as db:
            decision = db.query(Decision).filter_by(id=order_model.decision_id).first()
            if not decision or not decision.signal:
                return

            # Create position in DB
            position = DBPosition(
                position_id=f"POS_{order_model.id}",
                symbol=order_model.symbol,
                instrument_token=order_model.instrument_token,
                side=SideEnum.LONG if order_model.side == OrderSideEnum.BUY else SideEnum.SHORT,
                qty=order_model.filled_qty or order_model.qty,
                avg_price=order_model.average_price or order_model.price or 0.0,
                current_price=order_model.average_price or order_model.price or 0.0,
                stop_loss=decision.signal.stop_loss,
                take_profit_1=decision.signal.take_profit_1,
                take_profit_2=decision.signal.take_profit_2,
                risk_amount=decision.risk_amount,
                oco_group=None,  # Will be set by OCO manager
                strategy_name=order_model.strategy_name,
                entry_order_id=client_order_id,
                status=PositionStatusEnum.OPEN
            )
            db.add(position)
            db.commit()
            db.refresh(position)

            # Place stop/TP via OCO manager
            if self.oco_manager and decision.signal.stop_loss:
                oco_group_id = self.oco_manager.create_oco_group(
                    entry_order=order_model,
                    stop_price=decision.signal.stop_loss,
                    tp1_price=decision.signal.take_profit_1,
                    tp2_price=decision.signal.take_profit_2,
                    instrument_token=order_model.instrument_token,
                    qty=order_model.filled_qty or order_model.qty
                )
                position.oco_group = oco_group_id
                db.commit()

                # Publish OCO children created
                if self.redis_bus:
                    asyncio.create_task(self.redis_bus.publish_order({
                        "event": "OCO_CHILDREN",
                        "group": oco_group_id,
                        "position_id": position.position_id
                    }))

    async def on_child_filled(self, child_event: dict) -> None:
        """Called by OrderWatcher when a STOP or TP order is filled"""
        client_order_id = child_event.get("client_order_id")
        parent_group = child_event.get("parent_group")

        logger.info("Child order filled", client_order_id=client_order_id, group=parent_group)

        # Cancel siblings via OCO manager
        if self.oco_manager and parent_group:
            from packages.storage.models import Order
            order_model = None
            with get_db_session() as db:
                order_model = db.query(Order).filter_by(client_order_id=client_order_id).first()
            if order_model:
                self.oco_manager.on_child_fill(parent_group, order_model)

        # Update position and create trade
        from packages.core.persistence import update_order_status
        from packages.storage.database import get_db_session
        from packages.storage.models import (
            OrderStatusEnum,
            PositionStatusEnum,
            Trade,
            TradeActionEnum,
        )
        from packages.storage.models import Position as DBPosition

        update_order_status(
            client_order_id=client_order_id,
            status=OrderStatusEnum.FILLED,
            filled_qty=child_event.get("filled_qty"),
            average_price=child_event.get("average_price")
        )

        with get_db_session() as db:
            position = db.query(DBPosition).filter_by(oco_group=parent_group).first()
            if position:
                tag = child_event.get("tag", "")
                if tag == "STOP":
                    position.status = PositionStatusEnum.CLOSED
                    position.exit_reason = "STOP_LOSS"
                elif tag in ["TP1", "TP2"]:
                    if tag == "TP1":
                        position.qty -= child_event.get("filled_qty", 0)
                        position.exit_reason = "TP1_PARTIAL"
                    else:
                        position.status = PositionStatusEnum.CLOSED
                        position.exit_reason = "TP2_FULL"

                # Create trade record
                trade = Trade(
                    position_id=position.id,
                    action=TradeActionEnum.PARTIAL_EXIT if tag == "TP1" else TradeActionEnum.FULL_EXIT,
                    qty=child_event.get("filled_qty", 0),
                    price=child_event.get("average_price", 0.0),
                    fees=0.0,
                    risk_amount=position.risk_amount
                )
                db.add(trade)
                db.commit()

        # Publish OCO close
        if self.redis_bus:
            asyncio.create_task(self.redis_bus.publish_order({
                "event": "OCO_CLOSE",
                "group": parent_group,
                "client_order_id": client_order_id
            }))

    async def flatten_all(self, reason: str = "manual") -> None:
        """Kill switch - close all positions immediately"""
        from packages.core.alerts import alert_manager
        from packages.core.metrics import kill_switch_total
        from packages.storage.models import AuditActionEnum, AuditLog

        logger.critical("🚨 KILL SWITCH ACTIVATED - FLATTENING ALL POSITIONS", reason=reason)

        # Calculate open risk before flattening
        from packages.core.models import PositionStatus
        open_risk = sum(
            getattr(p, 'risk_amount', 0)
            for p in self.positions
            if getattr(p, 'status', None) == PositionStatus.OPEN
        ) if self.positions else 0.0

        positions_count = len([p for p in self.positions if getattr(p, 'status', None) == PositionStatus.OPEN]) if self.positions else 0

        # Record metric
        kill_switch_total.labels(reason=reason).inc()

        # Send alert
        alert_manager.alert_kill_switch(
            reason=reason,
            details={
                "open_risk_rupees": open_risk,
                "positions_count": positions_count
            }
        )

        # Audit log (backward-compatible: handles both details and data columns)
        from sqlalchemy import inspect

        from packages.storage.database import get_db_session

        with get_db_session() as db:
            # Check if details column exists
            try:
                columns = inspect(db.bind).get_columns("audit_logs")
                has_details = any(
                    c.get("name") == "details" or getattr(c, "name", None) == "details"
                    for c in columns
                )
            except Exception:
                # Fallback: assume details exists if we can't check
                has_details = True

            # Prepare action value (handle both Enum and string)
            action_value = AuditActionEnum.KILL_SWITCH
            # AuditActionEnum values are already strings, so use directly
            if isinstance(action_value, str):
                pass  # Already a string
            elif hasattr(action_value, 'value'):
                action_value = action_value.value
            else:
                action_value = str(action_value)

            # Create audit log with backward compatibility
            if has_details:
                audit_log = AuditLog(
                    action=action_value,
                    message=f"Kill switch activated: {reason}",
                    details={
                        "reason": reason,
                        "open_risk_rupees": open_risk,
                        "positions_count": positions_count
                    }
                )
            else:
                # Fallback to data column if details doesn't exist
                audit_log = AuditLog(
                    action=str(action_value),
                    message=f"Kill switch activated: {reason}",
                    data={
                        "reason": reason,
                        "open_risk_rupees": open_risk,
                        "positions_count": positions_count
                    }
                )
            db.add(audit_log)
            db.commit()

        self.is_paused = True

        await self._close_all_positions("KILL_SWITCH")

        logger.info("All positions flattened", reason=reason, open_risk_rupees=open_risk)

    async def _scan_supervisor(self) -> None:
        """Scan supervisor - never silently dies, always calls touch_scan()"""
        import time

        from packages.core.heartbeats import touch_scan
        from packages.core.metrics import scan_supervisor_state, scan_ticks_total

        logger.info("Main trading loop started (scan supervisor)", interval=self.scan_interval_seconds)

        try:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                try:
                    # Always mark a "tick" even if we early-return (market closed / paused)
                    try:
                        await self._scan_cycle()
                    finally:
                        scan_ticks_total.inc()  # Increment tick counter
                        touch_scan()
                except asyncio.CancelledError:
                    scan_supervisor_state.set(4)  # stopping
                    raise
                except Exception as e:
                    logger.exception("Scan cycle crashed; will retry in 1s", error=str(e))
                    await asyncio.sleep(1.0)
                    continue

                # Bounded sleep so config mistakes don't stall the loop
                dt = max(0.25, float(self.scan_interval_seconds))
                elapsed = time.perf_counter() - t0
                sleep_time = max(0.0, dt - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            scan_supervisor_state.set(4)  # stopping
            raise
        except Exception as e:
            scan_supervisor_state.set(3)  # exception
            logger.exception("Scan supervisor crashed; will restart", error=str(e))
            await asyncio.sleep(1.0)
            # Restart supervisor
            if self.is_running:
                self._stop.clear()
                scan_supervisor_state.set(1)  # running
                self._scan_task = asyncio.create_task(self._scan_supervisor(), name="scan-supervisor")
                logger.info("Scan supervisor restarted after exception")
        else:
            scan_supervisor_state.set(2)  # done

        logger.info("Main trading loop exiting (scan supervisor)")

    async def _main_loop(self) -> None:
        """Main trading loop (deprecated - use _scan_supervisor instead)"""
        logger.warning("_main_loop called - this should not happen, using _scan_supervisor instead")
        await self._scan_supervisor()

    async def _scan_cycle(self) -> None:
        """Execute one scan cycle: signals → rank → execute"""
        from packages.core.heartbeats import touch_scan
        touch_scan()
        if self.is_paused:
            return

        current_time = datetime.now()

        # Throttle scans
        if self.last_scan_time:
            elapsed = (current_time - self.last_scan_time).total_seconds()
            if elapsed < self.scan_interval_seconds:
                return

        self.last_scan_time = current_time

        logger.debug("Running scan cycle", timestamp=current_time.isoformat())

        # 1. Generate signals from all strategies
        all_signals = []

        for strategy in self.strategies:
            if not strategy.enabled:
                continue

            try:
                # Get market data for each instrument in universe
                universe_tokens = self.instrument_manager.get_universe_tokens()

                for token in universe_tokens[:20]:  # Limit for performance
                    instrument = self.instrument_manager.get_instrument(token)
                    if not instrument:
                        continue

                    # Get market data
                    tick = self.market_data_stream.get_latest_tick(token)
                    bars_1s = self.market_data_stream.get_bars(token, 1, n=60)
                    bars_5s = self.market_data_stream.get_bars(token, 5, n=100)

                    if not tick or not bars_5s:
                        continue

                    # Create strategy context
                    from packages.core.strategies.base import StrategyContext

                    context = StrategyContext(
                        timestamp=current_time,
                        instrument=instrument,
                        latest_tick=tick,
                        bars_1s=bars_1s,
                        bars_5s=bars_5s,
                        net_liquid=self._get_net_liquid(),
                        available_margin=self._get_available_margin(),
                        open_positions=len([p for p in self.positions if p.is_open])
                    )

                    # Generate signals
                    signals = strategy.generate_signals(context)
                    all_signals.extend(signals)

            except Exception as e:
                logger.error(f"Strategy {strategy.name} failed", error=str(e))

        if not all_signals:
            return

        self.signals_generated_today += len(all_signals)
        record_signals_per_cycle(len(all_signals))
        logger.info(f"Generated {len(all_signals)} signals from {len(self.strategies)} strategies")

        # Publish signals to Redis
        if self.redis_bus:
            for signal in all_signals:
                record_signal(signal.strategy_name, signal.instrument.symbol)
                asyncio.create_task(self.redis_bus.publish_signal({
                    "strategy": signal.strategy_name,
                    "symbol": signal.instrument.symbol,
                    "side": signal.side.value,
                    "entry_price": signal.entry_price,
                    "stop_loss": signal.stop_loss,
                    "confidence": signal.confidence
                }))

        # 2. Rank signals
        market_data_dict = {}
        for signal in all_signals:
            token = signal.instrument.token
            tick = self.market_data_stream.get_latest_tick(token)
            bars_5s = self.market_data_stream.get_bars(token, 5, n=100)
            if tick and bars_5s:
                market_data_dict[token] = (tick, bars_5s)

        ranked_opportunities = self.ranker.rank_signals(
            all_signals,
            market_data_dict
        )

        if not ranked_opportunities:
            logger.debug("No ranked opportunities after filtering")
            return

        logger.info(f"Top {len(ranked_opportunities)} ranked opportunities")

        # 3. Persist signals and execute top opportunities
        for rank, opportunity in enumerate(ranked_opportunities[:3], 1):  # Top 3 only
            if self.is_paused:
                break

            signal = opportunity.signal

            # Persist signal with features
            signal_model = persist_signal(
                signal=signal,
                score=opportunity.score,
                rank=rank,
                features=opportunity.features if hasattr(opportunity, 'features') else {},
                feature_scores=opportunity.feature_scores if hasattr(opportunity, 'feature_scores') else {},
                penalties=opportunity.penalties if hasattr(opportunity, 'penalties') else {}
            )
            record_signal_ranked(signal.strategy_name, signal.instrument.symbol, rank)

            # Risk check
            portfolio_risk = self._get_portfolio_risk()
            risk_check = self.risk_manager.check_signal(signal, portfolio_risk)

            # Persist decision
            decision_model = persist_decision(
                signal_model=signal_model,
                approved=risk_check.approved,
                risk_pct=risk_check.risk_pct,
                risk_amount=risk_check.risk_amount if hasattr(risk_check, 'risk_amount') else 0.0,
                position_size=risk_check.position_size,
                rr_expected=signal.expected_rr if hasattr(signal, 'expected_rr') else None,
                portfolio_heat_before=portfolio_risk.portfolio_heat_pct,
                portfolio_heat_after=portfolio_risk.portfolio_heat_pct,  # Will update after execution
                rejection_reasons=risk_check.reasons if not risk_check.approved else None
            )

            # Publish decision to Redis
            if self.redis_bus:
                asyncio.create_task(self.redis_bus.publish_decision({
                    "decision_id": decision_model.id,
                    "signal_id": signal_model.id,
                    "approved": risk_check.approved,
                    "position_size": risk_check.position_size,
                    "risk_pct": risk_check.risk_pct
                }))

            if not risk_check.approved:
                record_decision_rejected(signal.strategy_name, signal.instrument.symbol,
                                       risk_check.reasons[0] if risk_check.reasons else "unknown")
                logger.debug(
                    "Signal rejected by risk manager",
                    instrument=signal.instrument.tradingsymbol,
                    reasons=risk_check.reasons
                )
                continue

            record_decision_approved(signal.strategy_name, signal.instrument.symbol)

            # Execute signal with decision context (skip if dry_run mode)
            if app_config.execution.dry_run:
                logger.info(
                    "DRY_RUN: Signal approved but not executing",
                    strategy=signal.strategy_name,
                    instrument=signal.instrument.tradingsymbol,
                    position_size=risk_check.position_size
                )
            else:
                await self._execute_signal(signal, risk_check.position_size, decision_model)

    async def _execute_signal(self, signal: Signal, quantity: int, decision_model) -> None:
        """Execute a trading signal with persistence"""
        try:
            logger.info(
                "Executing signal",
                strategy=signal.strategy_name,
                instrument=signal.instrument.tradingsymbol,
                side=signal.side.value,
                quantity=quantity
            )

            # Place entry order
            result, order = await self.execution_engine.execute_signal(signal, quantity)

            if result in (OrderResult.SUCCESS, OrderResult.PARTIAL) and order:
                # Persist order
                order_model = persist_order(
                    decision_model=decision_model,
                    symbol=signal.instrument.symbol,
                    instrument_token=signal.instrument.token,
                    side="BUY" if signal.side == SignalSide.LONG else "SELL",
                    qty=quantity,
                    order_type="MARKET",
                    price=order.average_price,
                    tag="ENTRY",
                    parent_group=None,  # Will be set by OCO manager
                    broker_order_id=order.order_id if hasattr(order, 'order_id') else None,
                    strategy_name=signal.strategy_name
                )
                record_order_placed("MARKET", "PLACED")

                # Publish order to Redis
                if self.redis_bus:
                    asyncio.create_task(self.redis_bus.publish_order({
                        "event": "ENTRY_PLACED",
                        "client_order_id": order_model.client_order_id,
                        "symbol": signal.instrument.symbol,
                        "qty": quantity
                    }))

                # Create position
                position = Position(
                    position_id=f"POS_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.positions)}",
                    instrument=signal.instrument,
                    entry_time=datetime.now(),
                    entry_price=order.average_price,
                    quantity=order.filled_quantity,
                    side=signal.side,
                    current_price=order.average_price,
                    stop_loss=signal.stop_loss,
                    take_profit_1=signal.take_profit_1,
                    take_profit_2=signal.take_profit_2,
                    risk_amount=signal.risk_amount,
                    status=PositionStatus.OPEN,
                    entry_order_id=order.order_id,
                    strategy_name=signal.strategy_name
                )

                self.positions.append(position)
                self.orders_placed_today += 1

                # Notify strategy
                for strategy in self.strategies:
                    if strategy.name == signal.strategy_name:
                        strategy.on_position_opened()
                        break

                logger.info(
                    "Position opened",
                    position_id=position.position_id,
                    instrument=signal.instrument.tradingsymbol,
                    entry_price=order.average_price
                )

        except Exception as e:
            logger.error("Signal execution failed", error=str(e), signal=signal)

    async def _check_exits(self) -> None:
        """Check all positions for exit conditions"""
        if not self.positions:
            return

        # Update position prices
        for position in self.positions:
            if not position.is_open:
                continue

            tick = self.market_data_stream.get_latest_tick(position.instrument.token)
            if tick:
                position.current_price = tick.last_price
                position.update_pnl()

        # Get market data for exit manager
        market_data = {}
        for position in self.positions:
            if position.is_open:
                token = position.instrument.token
                tick = self.market_data_stream.get_latest_tick(token)
                bars_5s = self.market_data_stream.get_bars(token, 5, n=100)
                if tick and bars_5s:
                    market_data[token] = (tick, bars_5s)

        # Check exits
        portfolio_risk = self._get_portfolio_risk()
        exit_signals = self.exit_manager.check_exits(
            [p for p in self.positions if p.is_open],
            market_data,
            datetime.now(),
            portfolio_risk.daily_pnl_pct,
            portfolio_risk.net_liquid
        )

        # Execute exits
        for exit_signal in exit_signals:
            await self._close_position_by_id(exit_signal.position_id, exit_signal.reason.value)

    async def _close_position_by_id(self, position_id: str, reason: str) -> None:
        """Close a position by ID"""
        position = next((p for p in self.positions if p.position_id == position_id), None)

        if not position or not position.is_open:
            return

        try:
            # Close position
            exit_order = await self.execution_engine.close_position(position, reason)

            if exit_order:
                position.status = PositionStatus.CLOSED
                position.close_time = datetime.now()
                position.close_price = exit_order.average_price
                position.exit_order_id = exit_order.order_id

                # Calculate P&L
                if position.side == SignalSide.LONG:
                    gross_pnl = (exit_order.average_price - position.entry_price) * position.quantity
                else:
                    gross_pnl = (position.entry_price - exit_order.average_price) * position.quantity

                fees = self.risk_manager.estimate_fees(
                    position.instrument,
                    position.quantity,
                    position.entry_price,
                    exit_order.average_price
                )

                position.realized_pnl = gross_pnl - fees
                self.trades_completed_today += 1

                # Notify strategy
                for strategy in self.strategies:
                    if strategy.name == position.strategy_name:
                        strategy.on_position_closed(position.realized_pnl or 0.0)
                        break

                logger.info(
                    "Position closed",
                    position_id=position_id,
                    reason=reason,
                    pnl=position.realized_pnl
                )

        except Exception as e:
            logger.error(f"Failed to close position {position_id}", error=str(e))

    async def _close_all_positions(self, reason: str) -> None:
        """Close all open positions"""
        open_positions = [p for p in self.positions if p.is_open]

        for position in open_positions:
            await self._close_position_by_id(position.position_id, reason)

    async def _update_portfolio_state(self) -> None:
        """Update portfolio state and check limits"""
        portfolio_risk = self._get_portfolio_risk()

        # Check daily loss limit
        if portfolio_risk.is_daily_loss_breached:
            logger.critical("Daily loss limit breached - pausing trading")
            await self.pause()

        # Check portfolio heat
        if portfolio_risk.is_heat_limit_breached:
            logger.warning("Portfolio heat limit breached - pausing new entries")
            # Don't pause completely, just stop new entries

        # EOD square-off
        if self._should_square_off_eod():
            logger.info("EOD square-off time - closing all positions")
            await self._close_all_positions("EOD_SQUAREOFF")

    def _get_portfolio_risk(self) -> PortfolioRisk:
        """Get current portfolio risk state"""
        net_liquid = self._get_net_liquid()
        total_risk = sum([p.risk_amount for p in self.positions if p.is_open])
        unrealized_pnl = sum([p.unrealized_pnl for p in self.positions if p.is_open])
        realized_pnl_today = sum([p.realized_pnl or 0.0 for p in self.positions if not p.is_open])

        return self.risk_manager.update_portfolio_risk(
            net_liquid=net_liquid,
            positions=self.positions,
            realized_pnl_today=realized_pnl_today
        )

    def _get_net_liquid(self) -> float:
        """Get net liquid capital (simplified - would fetch from Kite in production)"""
        # In production, fetch from: self.kite.margins()['equity']['net']
        return 1000000.0  # Default 10 lakh for paper mode

    def _get_available_margin(self) -> float:
        """Get available margin"""
        portfolio_risk = self._get_portfolio_risk()
        return portfolio_risk.available_margin

    def _is_market_open(self) -> bool:
        """Check if market is currently open"""
        current_time = datetime.now().time()
        market_open = time(9, 15)
        market_close = time(15, 30)

        return market_open <= current_time <= market_close

    def _should_square_off_eod(self) -> bool:
        """Check if EOD square-off should happen"""
        if not app_config.market.eod_squareoff_enabled:
            return False

        current_time = datetime.now().time()
        eod_time = datetime.strptime(app_config.market.eod_squareoff_time, "%H:%M").time()

        return current_time >= eod_time

    def get_system_state(self) -> SystemState:
        """Get current system state"""
        from packages.core.models import PortfolioState, SystemState

        portfolio_risk = self._get_portfolio_risk()

        portfolio_state = PortfolioState(
            timestamp=datetime.now(),
            net_liquid=portfolio_risk.net_liquid,
            used_margin=portfolio_risk.used_margin,
            available_margin=portfolio_risk.available_margin,
            open_positions=[p for p in self.positions if p.is_open],
            total_positions=len([p for p in self.positions if p.is_open]),
            unrealized_pnl=portfolio_risk.unrealized_pnl,
            realized_pnl_today=portfolio_risk.realized_pnl_today,
            daily_pnl=portfolio_risk.daily_pnl,
            daily_pnl_pct=portfolio_risk.daily_pnl_pct,
            portfolio_heat=portfolio_risk.total_risk_amount,
            portfolio_heat_pct=portfolio_risk.portfolio_heat_pct,
            max_portfolio_heat_pct=app_config.risk.max_portfolio_heat_pct,
            daily_loss_limit=portfolio_risk.daily_loss_limit
        )

        wins = len([p for p in self.positions if not p.is_open and (p.realized_pnl or 0) > 0])
        losses = len([p for p in self.positions if not p.is_open and (p.realized_pnl or 0) <= 0])

        return SystemState(
            timestamp=datetime.now(),
            mode=settings.app_mode.value,
            is_paused=self.is_paused,
            is_market_open=self._is_market_open(),
            portfolio=portfolio_state,
            pending_signals=0,  # Would track pending signals
            active_orders=0,  # Would track from execution engine
            trades_today=self.trades_completed_today,
            wins_today=wins,
            losses_today=losses
        )

