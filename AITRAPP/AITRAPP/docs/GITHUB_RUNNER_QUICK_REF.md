# GitHub Runner Quick Reference

## One-Time Setup

```bash
make runner-setup
```

Or manually:
```bash
bash scripts/setup_github_runner.sh
```

## Daily Commands

```bash
# Check runner status
make runner-status

# View logs
make runner-logs

# Or directly:
cd ~/actions-runner
./svc.sh status
```

## Runner Management

```bash
cd ~/actions-runner

./svc.sh status      # Check if running
./svc.sh stop        # Stop service
./svc.sh start       # Start service
./svc.sh uninstall   # Remove service
```

## Verify Setup

1. **GitHub**: Settings → Actions → Runners → Should see `paper-runner-mac` as **Online**
2. **Test**: GitHub → Actions → Run workflow → Select "PAPER — Preopen Checks"
3. **Check logs**: `tail -f ~/actions-runner/_diag/*.log`

## Troubleshooting

### Runner not online
```bash
cd ~/actions-runner
./svc.sh start
./svc.sh status
```

### Docker not running
```bash
# Docker Desktop
open -a Docker

# Colima
colima start
```

### Port 8000 in use
```bash
lsof -nP -iTCP:8000
# Kill process or use PORT=8010 in workflows
```

## Workflow Schedule

- **08:40 IST** (03:10 UTC): Pre-live gate
- **08:50 IST** (03:20 UTC): Paper E2E
- **15:35 IST** (10:05 UTC): Day-2 artifacts archive

All workflows now run on `self-hosted` runner with label `paper-runner`.

## Documentation

Full setup guide: `docs/GITHUB_RUNNER_SETUP.md`


