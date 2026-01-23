# Self-Hosted GitHub Actions Runner Setup (macOS)

This guide sets up a self-hosted GitHub Actions runner on macOS (Apple Silicon) to execute scheduled PAPER workflows.

## Quick Start

Run the automated setup script:

```bash
bash scripts/setup_github_runner.sh
```

The script will:
1. Install Docker (Desktop or Colima)
2. Install `jq` and `coreutils`
3. Download and configure the GitHub Actions runner
4. Install as a LaunchAgent (auto-start on login)
5. Set up sleep prevention

## Manual Setup

If you prefer manual setup or the script fails:

### 1. Install Docker

**Option A: Docker Desktop (recommended)**
```bash
brew install --cask docker
open -a Docker  # Grant permissions when prompted
# Wait until Docker Desktop shows "Running"
```

**Option B: Colima (CLI only)**
```bash
brew install colima docker docker-compose
colima start --arch aarch64 --cpu 4 --memory 6
docker ps  # Verify it works
```

### 2. Install CLI Tools

```bash
brew install jq coreutils
```

### 3. Create Runner Directory

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
```

### 4. Download Runner

```bash
RUNNER_VERSION="3.630.0"
curl -o actions-runner.tar.gz -L \
  "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"
tar xzf actions-runner.tar.gz
```

### 5. Configure Runner

Get the registration token from:
- GitHub → Your Repo → Settings → Actions → Runners → New self-hosted runner → macOS

Then run:

```bash
./config.sh \
  --url https://github.com/<OWNER>/<REPO> \
  --token <RUNNER_TOKEN> \
  --name paper-runner-mac \
  --labels paper-runner,mac \
  --work _work
```

### 6. Install as LaunchAgent

```bash
./svc.sh install
./svc.sh start
./svc.sh status
```

### 7. Prevent Sleep During Runs

**Option A: System Settings**
- System Settings → Battery → Options → Prevent automatic sleeping on power adapter

**Option B: Terminal**
```bash
caffeinate -dimsu &  # Prevents sleep
```

## Verify Setup

1. **Check runner status:**
   ```bash
   cd ~/actions-runner
   ./svc.sh status
   ```

2. **Check GitHub:**
   - GitHub → Settings → Actions → Runners
   - Should see `paper-runner-mac` as **Online**

3. **Test workflow:**
   - GitHub → Actions → Run workflow (for "PAPER — Preopen Checks")
   - Confirm job runs on `paper-runner-mac`

## Runner Commands

```bash
cd ~/actions-runner

./svc.sh status      # Check status
./svc.sh stop        # Stop service
./svc.sh start       # Start service
./svc.sh uninstall   # Remove service
./run.sh             # Run manually (for testing)
```

## Logs

Runner logs are in:
```bash
~/actions-runner/_diag/*.log
```

View recent logs:
```bash
tail -f ~/actions-runner/_diag/Runner_*.log
```

## Troubleshooting

### Docker not found
```bash
# Check Docker is running
docker ps

# If using Colima
colima status
colima start

# If using Docker Desktop
open -a Docker
```

### Port 8000 already in use
```bash
# Check what's using port 8000
lsof -nP -iTCP:8000

# Kill the process or use a different port
# In workflows, you can set PORT=8010
```

### Runner not appearing in GitHub
1. Check runner is running: `cd ~/actions-runner && ./svc.sh status`
2. Check logs: `tail -f ~/actions-runner/_diag/*.log`
3. Verify network connectivity (runner needs to reach GitHub)
4. Re-run `./config.sh` if token expired

### Workflow fails with "self-hosted runner not found"
- Ensure workflow YAML has: `runs-on: self-hosted` and `labels: [paper-runner]`
- Verify runner is online in GitHub → Settings → Actions → Runners
- Check runner labels match: `paper-runner,mac`

### Services (Postgres/Redis) not starting
```bash
# Check Docker Compose
cd /path/to/repo
docker compose ps
docker compose logs postgres redis

# Restart services
docker compose restart postgres redis
```

## Workflow Updates

All workflows have been updated to use the self-hosted runner:

- `.github/workflows/paper-e2e.yml` - Uses `runs-on: self-hosted, labels: [paper-runner]`
- `.github/workflows/prelive-gate.yml` - Uses `runs-on: self-hosted, labels: [paper-runner]`
- `.github/workflows/archive-day2-artifacts.yml` - Uses `runs-on: self-hosted, labels: [paper-runner]`

The `paper-e2e.yml` workflow now starts Postgres and Redis using `docker compose` instead of GitHub Actions services.

## Security Notes

⚠️ **Important:**
- The runner has access to your repository code and secrets
- Keep your Mac secure (screen lock, encrypted disk)
- Don't run untrusted workflows
- Regularly update the runner: `cd ~/actions-runner && ./svc.sh stop && ./svc.sh uninstall`, then re-run setup

## Maintenance

### Update Runner

```bash
cd ~/actions-runner
./svc.sh stop
./svc.sh uninstall

# Download latest version
RUNNER_VERSION="3.630.0"  # Check latest at https://github.com/actions/runner/releases
curl -o actions-runner.tar.gz -L \
  "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"
tar xzf actions-runner.tar.gz

# Reconfigure (use same token or get new one)
./config.sh --url https://github.com/<OWNER>/<REPO> --token <TOKEN> --name paper-runner-mac --labels paper-runner,mac

./svc.sh install
./svc.sh start
```

### Remove Runner

```bash
cd ~/actions-runner
./svc.sh stop
./svc.sh uninstall
rm -rf ~/actions-runner

# Also remove from GitHub:
# GitHub → Settings → Actions → Runners → Remove runner
```

## macOS-Specific Notes

- **Cron in Actions**: GitHub Actions cron is in UTC (already accounted for in workflow YAMLs)
- **Docker permissions**: Docker Desktop may ask for permissions; grant them
- **Port conflicts**: Ensure port 8000 is free, or use `PORT=8010` in workflows
- **Sleep prevention**: Use `caffeinate` or System Settings to prevent sleep during runs
- **Time zone**: Workflows use IST (Asia/Kolkata) but cron is UTC

## Next Steps

After setup:
1. ✅ Verify runner is online in GitHub
2. ✅ Test with a manual workflow run
3. ✅ Monitor first scheduled run (08:40 IST for prelive-gate, 08:50 IST for paper-e2e)
4. ✅ Check Telegram notifications (if configured)

## Support

If you encounter issues:
1. Check runner logs: `~/actions-runner/_diag/*.log`
2. Check workflow logs in GitHub Actions
3. Verify Docker and services are running
4. Ensure network connectivity to GitHub


