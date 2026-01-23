# Ops Tools - LIVE Switch Convenience Pack

## Quick Setup

### 1. Load Aliases
```bash
# Add to ~/.zshrc or ~/.bashrc
source /path/to/AITRAPP/ops/aliases.sh
```

**Available aliases:**
- `killnow` - Flatten all positions
- `pause` - Pause trading
- `resume` - Resume trading
- `live` - Switch to LIVE mode
- `paper` - Switch to PAPER mode
- `abort` - Immediate abort (pause + flatten + PAPER)
- `state` - Get system state
- `risk` - Get risk status
- `positions` - Get positions
- `metrics` - Get metrics
- `health` - Health check

### 2. Canary Pre-Check
```bash
./ops/canary_precheck.sh
```

Validates:
- Leader lock = 1
- Heartbeats healthy
- Flatten ≤ 2s
- Zero positions

### 3. Create Tmux Dashboard
```bash
./ops/live.sh dashboard
tmux attach -t live
```

**5 Panes:**
1. Key metrics (refreshes every 5s)
2. Positions/Heat/P&L (refreshes every 2s)
3. Redis event feed (real-time)
4. Audit log tail (real-time)
5. Risk caps (refreshes every 5s)

### 4. Full LIVE Sequence
```bash
./ops/live.sh full
```

Runs:
1. Canary pre-check
2. Creates dashboard (optional)
3. Switches to LIVE
4. Starts monitoring with snapshots

---

## Individual Commands

### Dashboard Only
```bash
./ops/live.sh dashboard
```

### Pre-Check Only
```bash
./ops/live.sh precheck
```

### Switch to LIVE Only
```bash
./ops/live.sh switch
```

### Monitor with Snapshots
```bash
./ops/live.sh monitor
```

### Immediate Abort
```bash
./ops/abort.sh
# Or use alias: abort
```

---

## After First Hour (If Clean)

### Bump Caps
```bash
# Edit config
vim configs/app.yaml
# Change:
#   per_trade_risk_pct: 0.30
#   max_portfolio_heat_pct: 1.2

# Restart API
# (Kill and restart with new config)
```

### Post-Close
```bash
make post-close
psql $DATABASE_URL -f scripts/reconcile_db.sql
```

---

## Tips

- **Keep tmux dashboard visible** during LIVE switch
- **Use `abort` alias** for immediate rollback
- **Monitor first hour** closely
- **Check incident snapshots** in `reports/incidents/` if issues occur

---

## Troubleshooting

### Tmux not found
```bash
brew install tmux
```

### jq not found
```bash
brew install jq
```

### API not running
```bash
make paper
```

### Dashboard panes not updating
- Check API is running: `curl localhost:8000/health`
- Check Redis is running: `docker compose ps redis`
- Restart dashboard: `tmux kill-session -t live && ./ops/live.sh dashboard`

