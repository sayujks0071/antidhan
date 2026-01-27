# Final Deployment Checklist

## 1. Risk Limits & Hygiene
- [ ] **Max Daily Loss**: Set `DAILY_LOSS_LIMIT` in environment (e.g., 2% of Capital).
- [ ] **Max Position Size**: Ensure `quantity` or position sizing logic matches live account size.
- [ ] **Slippage Protection**: Use Limit Orders where possible, or Market with Protection.
- [ ] **Broker Tokens**: Verify `KITE_ACCESS_TOKEN` / `DHAN_ACCESS_TOKEN` are valid.

## 2. Symbol Mapping (NSE/NFO)
- [ ] **NIFTY**: Ensure symbol `NIFTY 50` maps to underlying token correctly.
- [ ] **Options**: Verify `NFO` symbol format (e.g., `NIFTY23AUG19500CE`).
- [ ] **Liquid Contracts**: Strategy should filter for OI/Volume > Threshold.

## 3. Strategy Configuration
### SuperTrend VWAP
- [ ] `use_regime_filter`: Set to `True` for live trading.
- [ ] `atr_sl_mult`: Recommended `2.0`.
- [ ] `atr_tp_mult`: Recommended `4.0`.

### ORB
- [ ] `use_regime_filter`: Set to `True` to avoid trading against daily trend.
- [ ] `atr_sl_mult`: Recommended `2.0`.

### NIFTY Greeks Enhanced
- [ ] `min_adx`: Recommended `25` to ensure trend strength.
- [ ] `iv_rank_min`: Avoid low IV environments if buying options.

## 4. Operational
- [ ] **Time Sync**: Ensure server time is synced with NTP.
- [ ] **Monitoring**: Run `monitor_trades.py` alongside strategies.
- [ ] **Failover**: Have a manual kill switch (e.g., `pkill -f python`).

## 5. Walk-Forward Validation
- [ ] Before scaling up, run strategy with `0.1x` size for 1 week.
- [ ] Compare Live executions with Backtest signals for the same period.
