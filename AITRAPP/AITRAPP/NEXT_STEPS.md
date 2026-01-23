# Production-Grade Implementation - Next Steps

## ✅ Completed

1. **Database Models** - SQLAlchemy models for Instrument, Signal, Decision, Order, Position, Trade, RiskEvent, AuditLog
2. **Alembic Setup** - Migration framework configured
3. **OCO Manager** - App-level OCO with sibling cancellation
4. **OrderWatcher** - Monitors broker orders and enforces OCO invariants
5. **Hardened Risk Gates** - `can_enter()` function with hard blocks
6. **Redis Pub/Sub** - Event bus for decoupling components
7. **Prometheus Metrics** - Comprehensive observability

## 🔄 In Progress

8. **Persistence Integration** - Wire orchestrator to persist signals/decisions/orders

## 📋 Remaining Tasks

### Today (T-0 → T-1)

1. **Wire Persistence in Orchestrator**
   - Persist signals with features + config_sha
   - Persist decisions with client_plan_id (idempotency)
   - Persist orders with client_order_id
   - Link everything with foreign keys

2. **Update FastAPI Endpoints**
   - Add `/pause` endpoint
   - Add `/flatten` endpoint  
   - Add `/mode` endpoint with LIVE gate
   - Add `/metrics` endpoint (Prometheus)
   - Add `/risk` endpoint (current risk state)

3. **Integrate OCO Manager**
   - Wire OCO manager into execution engine
   - On entry fill → place stop/TP
   - On child fill → cancel siblings

4. **Start OrderWatcher**
   - Run as background task
   - Monitor order status updates
   - Trigger OCO logic on fills

5. **Redis Integration**
   - Publish signals to Redis
   - Publish decisions to Redis
   - Publish orders to Redis
   - Publish risk updates to Redis

### This Week (T-2 → T-5)

6. **Next.js Dashboard**
   - Socket.IO client
   - Subscribe to Redis channels
   - Display: ranks, positions, P&L, heat, kill switch

7. **Workers (Celery)**
   - Pre-open instrument sync (08:30 IST)
   - Options chain refresh (every minute)
   - EOD cleanup tasks

8. **Replay Test Suite**
   - Determinism tests (same inputs → same outputs)
   - Chaos tests (WS drop, partial fills, rejections)

9. **Paper Burn-in**
   - 3 full sessions
   - Tight guardrails
   - Session reports

### Go-Live Gate

10. **LIVE Mode Gate**
    - Typed confirmation required
    - Session-scoped (resets to PAPER on restart)

11. **E2E Runbook**
    - Start/stop procedures
    - Incident SOP
    - Telegram alerts (optional)

---

## Key Implementation Notes

### Persistence Pattern

```python
# In orchestrator._scan_cycle()
with get_db_session() as db:
    # 1. Persist signals
    signal_model = Signal(
        symbol=signal.instrument.symbol,
        instrument_token=signal.instrument.token,
        side=signal.side,
        strategy=signal.strategy_name,
        score=opportunity.score,
        features=opportunity.features,
        feature_scores=opportunity.feature_scores,
        config_sha=app_config.config_sha,
        rationale=signal.rationale
    )
    db.add(signal_model)
    db.flush()
    
    # 2. Persist decision
    decision_model = Decision(
        signal_id=signal_model.id,
        client_plan_id=f"PLAN_{signal_model.id}_{datetime.utcnow().isoformat()}",
        mode=settings.app_mode.value,
        risk_perc=risk_check.risk_pct,
        risk_amount=risk_check.risk_amount,
        position_size=risk_check.position_size,
        status=DecisionStatusEnum.PLANNED
    )
    db.add(decision_model)
    db.commit()
```

### OCO Integration

```python
# In execution engine
oco_group_id = oco_manager.create_oco_group(
    entry_order=entry_order,
    stop_price=signal.stop_loss,
    tp1_price=signal.take_profit_1,
    tp2_price=signal.take_profit_2
)

# On entry fill (in OrderWatcher)
oco_manager.on_entry_fill(oco_group_id)

# On child fill (in OrderWatcher)
oco_manager.on_child_fill(oco_group_id, filled_order)
```

### Redis Publishing

```python
# After generating signals
await redis_bus.publish_signal({
    "signal_id": signal_model.id,
    "strategy": signal.strategy_name,
    "symbol": signal.instrument.symbol,
    "score": opportunity.score,
    "features": opportunity.features
})

# After making decision
await redis_bus.publish_decision({
    "decision_id": decision_model.id,
    "signal_id": signal_model.id,
    "approved": risk_check.approved,
    "position_size": risk_check.position_size
})
```

---

## Testing Checklist

- [ ] Kill switch flattens ≤ 2s
- [ ] Heat/daily-loss blocks new entries
- [ ] EOD flat exactly at 15:25 IST
- [ ] Every trade has audit trail (signal→decision→orders→trades)
- [ ] OCO siblings cancel correctly
- [ ] OrderWatcher handles partial fills
- [ ] Redis events reach dashboard
- [ ] Prometheus metrics exposed
- [ ] Config SHA tracked on all decisions

---

## Run Commands

```bash
# Run migrations
alembic upgrade head

# Start in PAPER mode
make paper

# Test kill switch
curl -X POST http://localhost:8000/pause
curl -X POST http://localhost:8000/flatten

# Check metrics
curl http://localhost:8000/metrics

# Check risk state
curl http://localhost:8000/risk
```
