# Week-1 Mini Backlog (Non-Blocking, High ROI)

## 🎯 Quick Wins for Post-LIVE Improvements

### 1. Risk Banner on Dashboard ⚠️

**Goal:** Visual indicator when portfolio heat ≥75% of cap

**Implementation:**
- Add to dashboard header/top bar
- Color: Green (<50%), Yellow (50-75%), Red (≥75%)
- Update: Real-time from `trader_portfolio_heat_rupees` metric

**Files to Update:**
- `apps/web/` (dashboard component)
- Or add to API response: `GET /state` → include `risk_banner_color`

**Priority:** Medium  
**Effort:** 1-2 hours

---

### 2. Session Tagging 📝

**Goal:** Log `SESSION=YYYY-MM-DD-LIVE-CANARY` into every audit row

**Implementation:**
```python
# In packages/core/persistence.py
SESSION_ID = f"{datetime.now().strftime('%Y-%m-%d')}-{settings.app_mode.value}-CANARY"

# Add to all audit logs
audit_log.session_id = SESSION_ID
```

**Files to Update:**
- `packages/core/persistence.py` - Add session_id constant
- `packages/storage/models.py` - Add `session_id` column to `AuditLog`
- `alembic/versions/` - Migration for new column

**Priority:** High (forensics)  
**Effort:** 2-3 hours

---

### 3. Slippage & Latency Persistence 📊

**Goal:** Persist per-trade slippage & latency; auto-update slippage model daily

**Implementation:**
```python
# In packages/core/execution.py
# After order fill:
slippage = abs(fill_price - expected_price) / expected_price
latency_ms = (fill_time - order_time).total_seconds() * 1000

# Persist to Trade model
trade.slippage_bps = slippage * 10000
trade.latency_ms = latency_ms

# Daily update slippage model
# Calculate average slippage per instrument/strategy
# Update config.slippage_bps dynamically
```

**Files to Update:**
- `packages/storage/models.py` - Add `slippage_bps`, `latency_ms` to `Trade`
- `packages/core/execution.py` - Calculate and persist slippage/latency
- `packages/core/config.py` - Add dynamic slippage model
- `alembic/versions/` - Migration for new fields

**Priority:** High (improves accuracy)  
**Effort:** 4-6 hours

---

### 4. NSE Holiday/Event Calendar 📅

**Goal:** Auto-fetch at 08:00 IST; wire placeholder

**Implementation:**
```python
# In packages/core/market_hours.py
async def fetch_nse_calendar():
    """Fetch NSE trading holidays and events"""
    # Option 1: NSE API (if available)
    # Option 2: Scrape NSE website
    # Option 3: Use third-party API (e.g., tradingview, alpha vantage)
    
    holidays = []  # List of YYYY-MM-DD dates
    events = []   # List of event dicts (CPI, RBI, expiry, etc.)
    
    return holidays, events

# Schedule daily fetch at 08:00 IST
# Update MarketHoursGuard with fetched holidays
```

**Files to Update:**
- `packages/core/market_hours.py` - Implement `fetch_nse_calendar()`
- `packages/core/orchestrator.py` - Schedule daily fetch
- `packages/storage/models.py` - Add `TradingCalendar` model (optional)

**Priority:** Medium  
**Effort:** 3-4 hours

---

## 📋 Implementation Order

1. **Session Tagging** (High priority, easy)
2. **Slippage & Latency** (High priority, medium effort)
3. **Risk Banner** (Medium priority, easy)
4. **NSE Calendar** (Medium priority, medium effort)

---

## 🎯 Success Criteria

- [ ] Risk banner shows red when heat ≥75%
- [ ] All audit logs have session_id
- [ ] Slippage model updates daily
- [ ] NSE calendar fetched at 08:00 IST
- [ ] Holidays/events block entries appropriately

---

## 📝 Notes

- All items are **non-blocking** for LIVE launch
- Can be implemented incrementally
- High ROI: improves observability and accuracy
- Test in PAPER mode before deploying to LIVE

