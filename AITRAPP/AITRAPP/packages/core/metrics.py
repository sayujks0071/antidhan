"""Prometheus metrics for observability"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import Response

REGISTRY = CollectorRegistry()

# Counters
signals_total = Counter(
    'trader_signals_total',
    'Signals generated',
    ['strategy', 'symbol'],
    registry=REGISTRY
)

decisions_total = Counter(
    'trader_decisions_total',
    'Decisions planned',
    ['strategy', 'symbol', 'status'],
    registry=REGISTRY
)

orders_placed_total = Counter(
    'trader_orders_placed_total',
    'Orders placed',
    ['order_type', 'status'],
    registry=REGISTRY
)

orders_filled_total = Counter(
    'trader_orders_filled_total',
    'Orders filled',
    ['order_type'],
    registry=REGISTRY
)

oco_children_total = Counter(
    'trader_oco_children_created_total',
    'OCO children created',
    registry=REGISTRY
)

risk_blocks_total = Counter(
    'trader_risk_blocks_total',
    'Entries blocked by risk',
    ['reason'],
    registry=REGISTRY
)

retries_total = Counter(
    'trader_retries_total',
    'Retries (API/ws)',
    ['type'],
    registry=REGISTRY
)

# Gauges
positions_open = Gauge(
    'trader_positions_open',
    'Open positions',
    ['strategy'],
    registry=REGISTRY
)

portfolio_heat_rupees = Gauge(
    'trader_portfolio_heat_rupees',
    'Portfolio heat in ₹',
    registry=REGISTRY
)

daily_pnl_rupees = Gauge(
    'trader_daily_pnl_rupees',
    'Realized daily P&L in ₹',
    registry=REGISTRY
)

is_leader = Gauge(
    'trader_is_leader',
    'Leader lock status (1=leader, 0=not leader)',
    ['instance_id'],
    registry=REGISTRY
)

throttle_queue_depth = Gauge(
    'trader_throttle_queue_depth',
    'Rate limit throttle queue depth',
    ['type'],
    registry=REGISTRY
)

marketdata_heartbeat_seconds = Gauge(
    'trader_marketdata_heartbeat_seconds',
    'Seconds since last market data event',
    registry=REGISTRY
)

order_stream_heartbeat_seconds = Gauge(
    'trader_order_stream_heartbeat_seconds',
    'Seconds since last order event',
    registry=REGISTRY
)

scan_heartbeat_seconds = Gauge(
    'trader_scan_heartbeat_seconds',
    'Seconds since last orchestrator scan',
    registry=REGISTRY
)

scan_interval_seconds = Gauge(
    'trader_scan_interval_seconds',
    'Configured scan interval seconds',
    registry=REGISTRY
)

scan_ticks_total = Counter(
    'trader_scan_ticks_total',
    'Total orchestrator scan ticks',
    registry=REGISTRY
)

scan_supervisor_state = Gauge(
    'trader_scan_supervisor_state',
    'Scan supervisor state: 0=stopped, 1=running, 2=done, 3=exception, 4=stopping',
    registry=REGISTRY
)

kill_switch_total = Counter(
    'trader_kill_switch_total',
    'Kill switch activations',
    ['reason'],
    registry=REGISTRY
)

leader_changes_total = Counter(
    'trader_leader_changes_total',
    'Number of leader lock state changes',
    registry=REGISTRY
)

# Pre-live gate observability
prelive_day2_pass = Gauge(
    'trader_prelive_day2_pass',
    'Day-2 scorer PASS (0/1)',
    registry=REGISTRY
)

prelive_day2_age = Gauge(
    'trader_prelive_day2_age_seconds',
    'Age of latest Day-2 JSON in seconds',
    registry=REGISTRY
)

# Histograms
tick_to_decision_ms = Histogram(
    'trader_tick_to_decision_ms',
    'Latency tick→decision (ms)',
    buckets=[5, 10, 25, 50, 100, 150, 250, 500, 1000],
    registry=REGISTRY
)

order_latency_ms = Histogram(
    'trader_order_latency_ms',
    'Order placement latency (ms)',
    buckets=[10, 25, 50, 100, 150, 250, 500, 1000, 2000],
    registry=REGISTRY
)

# Legacy aliases for backward compatibility
signals_generated = signals_total

signals_ranked = Counter(
    'aitrapp_signals_ranked_total',
    'Total signals ranked',
    ['strategy', 'symbol', 'rank']
)

# Decision metrics
decisions_approved = Counter(
    'aitrapp_decisions_approved_total',
    'Total decisions approved',
    ['strategy', 'symbol']
)

decisions_rejected = Counter(
    'aitrapp_decisions_rejected_total',
    'Total decisions rejected',
    ['strategy', 'symbol', 'reason']
)

# Order metrics
orders_placed = Counter(
    'aitrapp_orders_placed_total',
    'Total orders placed',
    ['order_type', 'status']
)

orders_filled = Counter(
    'aitrapp_orders_filled_total',
    'Total orders filled',
    ['order_type']
)

order_latency = Histogram(
    'aitrapp_order_latency_seconds',
    'Order placement latency',
    ['order_type'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

# Position metrics
positions_open = Gauge(
    'aitrapp_positions_open',
    'Number of open positions',
    ['strategy']
)

position_pnl = Gauge(
    'aitrapp_position_pnl',
    'Position P&L',
    ['position_id', 'symbol']
)

# Risk metrics
portfolio_heat = Gauge(
    'aitrapp_portfolio_heat_percent',
    'Portfolio heat percentage'
)

daily_pnl = Gauge(
    'aitrapp_daily_pnl',
    'Daily P&L'
)

risk_events = Counter(
    'aitrapp_risk_events_total',
    'Total risk events',
    ['event_type', 'severity']
)

# WebSocket metrics
ws_reconnects = Counter(
    'aitrapp_ws_reconnects_total',
    'Total WebSocket reconnects'
)

ws_messages_received = Counter(
    'aitrapp_ws_messages_received_total',
    'Total WebSocket messages received',
    ['message_type']
)

# API metrics
api_requests = Counter(
    'aitrapp_api_requests_total',
    'Total API requests',
    ['endpoint', 'method', 'status']
)

api_latency = Histogram(
    'aitrapp_api_latency_seconds',
    'API request latency',
    ['endpoint', 'method'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

# Orchestrator metrics
scan_cycle_duration = Histogram(
    'aitrapp_scan_cycle_duration_seconds',
    'Scan cycle duration',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

signals_per_cycle = Histogram(
    'aitrapp_signals_per_cycle',
    'Number of signals generated per cycle',
    buckets=[0, 1, 5, 10, 20, 50, 100]
)


def get_metrics() -> bytes:
    """Get Prometheus metrics in text format"""
    return generate_latest(REGISTRY)


def metrics_app():
    """FastAPI/Starlette metrics endpoint response"""
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


def record_signal(strategy: str, symbol: str):
    """Record signal generation"""
    signals_total.labels(strategy=strategy, symbol=symbol).inc()


def record_signal_ranked(strategy: str, symbol: str, rank: int):
    """Record signal ranking"""
    signals_total.labels(strategy=strategy, symbol=symbol).inc()  # Count as signal


def record_decision_approved(strategy: str, symbol: str):
    """Record approved decision"""
    decisions_total.labels(strategy=strategy, symbol=symbol, status="approved").inc()


def record_decision_rejected(strategy: str, symbol: str, reason: str):
    """Record rejected decision"""
    decisions_total.labels(strategy=strategy, symbol=symbol, status="rejected").inc()
    risk_blocks_total.labels(reason=reason).inc()


def record_order_placed(order_type: str, status: str):
    """Record order placement"""
    orders_placed_total.labels(order_type=order_type, status=status).inc()


def record_order_filled(order_type: str):
    """Record order fill"""
    orders_filled_total.labels(order_type=order_type).inc()


def record_order_latency(order_type: str, latency: float):
    """Record order placement latency"""
    order_latency.labels(order_type=order_type).observe(latency)


def update_positions_open(strategy: str, count: int):
    """Update open positions count"""
    positions_open.labels(strategy=strategy).set(count)


def update_position_pnl(position_id: str, symbol: str, pnl: float):
    """Update position P&L"""
    position_pnl.labels(position_id=position_id, symbol=symbol).set(pnl)


def update_portfolio_heat(heat_rupees: float):
    """Update portfolio heat in rupees"""
    portfolio_heat_rupees.set(heat_rupees)


def update_daily_pnl(pnl: float):
    """Update daily P&L in rupees"""
    daily_pnl_rupees.set(pnl)


def record_risk_event(event_type: str, severity: str):
    """Record risk event"""
    risk_events.labels(event_type=event_type, severity=severity).inc()


def record_ws_reconnect():
    """Record WebSocket reconnect"""
    ws_reconnects.inc()


def record_ws_message(message_type: str):
    """Record WebSocket message"""
    ws_messages_received.labels(message_type=message_type).inc()


def record_api_request(endpoint: str, method: str, status: int):
    """Record API request"""
    api_requests.labels(endpoint=endpoint, method=method, status=str(status)).inc()


def record_api_latency(endpoint: str, method: str, latency: float):
    """Record API latency"""
    api_latency.labels(endpoint=endpoint, method=method).observe(latency)


def record_scan_cycle_duration(duration: float):
    """Record scan cycle duration"""
    scan_cycle_duration.observe(duration)


def record_signals_per_cycle(count: int):
    """Record signals per cycle"""
    signals_per_cycle.observe(count)

