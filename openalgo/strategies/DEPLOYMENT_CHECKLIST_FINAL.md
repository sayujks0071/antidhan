# Final Deployment Checklist

## 1. Risk Management Limits
- [ ] **Max Capital Allocation per Strategy:** ₹5,00,000
- [ ] **Max Drawdown Limit (Circuit Breaker):** 2% of Capital / Day
- [ ] **Max Open Positions:** 2 per Symbol

## 2. Strategy-Specific Checks

### ORB Strategy (NIFTY/BANKNIFTY)
- [ ] **Trend Filter:** Verify Daily EMA50 is calculated correctly before 9:15 AM.
- [ ] **Gap Check:** Ensure Pre-market Gap % is available at 9:08 AM.
- [ ] **Time Window:** 15 Minute Range (9:15 - 9:30).

### SuperTrend VWAP (Intraday Stocks/Index)
- [ ] **Sector Benchmark:** Ensure `NIFTY BANK` or relevant sector data is streaming.
- [ ] **Volume Data:** Ensure volume is accurate (not tick volume if possible, or consistent tick vol).
- [ ] **RSI Calculation:** Warm-up data (at least 20 days) loaded for Sector RSI.

### Iron Condor (Weekly Options)
- [ ] **VIX Feed:** Ensure `INDIA VIX` data is live.
- [ ] **Execution Day:** Typically Wednesday/Thursday.
- [ ] **Margin:** Ensure sufficient margin for 4 legs (approx ₹1.5L per lot).

## 3. Operational Checks
- [ ] **API Token:** Valid Token for NSE F&O.
- [ ] **Symbol Mapping:** Verify Option Symbol format matches Broker (e.g., `NIFTY26JAN24500CE`).
- [ ] **Emergency Exit:** `python3 openalgo/scripts/emergency_squareoff.py` is ready.

## 4. Slippage Assumptions
- **NIFTY Options:** 2-3 pts
- **Stock Futures:** 0.05%
- **Impact:** Use Limit Orders where possible (implemented in `SmartOrder`).
