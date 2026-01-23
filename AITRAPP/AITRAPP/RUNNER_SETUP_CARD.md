# Self-Hosted Runner Setup Card

## 1) Register & Start Runner (One-Time)

```bash
# From your repo
make runner-setup

# When prompted, paste:
#   Repo URL: https://github.com/<OWNER>/<REPO>
#   Runner token: (GitHub → Repo → Settings → Actions → Runners → New self-hosted runner → macOS)
```

**Quick sanity:**
```bash
make runner-status      # should show "running"
make runner-logs        # tail runner logs
make runner-verify      # comprehensive check
```

In GitHub → **Settings → Actions → Runners**, you should see `paper-runner-mac` **Online**.

## 2) Make Sure Docker is Running

Pick one:
```bash
open -a Docker    # Docker Desktop, wait till it shows "Running"
# OR
colima start --arch aarch64 --cpu 4 --memory 6
```

## 3) Prove a Workflow Runs on Your Mac

In GitHub → **Actions** → pick any of:
- **PAPER — Preopen Checks** (prelive-gate)
- **paper-e2e** (manual)
- **Archive Day-2 Artifacts**

Click **Run workflow**. Confirm it runs on `self-hosted / paper-runner`.

## 4) Scheduled Crons

- **08:40 IST** (03:10 UTC): Pre-live gate checks (PAPER)
- **08:50 IST** (03:20 UTC): Paper E2E test
- **15:35 IST** (10:05 UTC): Post-close report + Day-2 scoring

They'll run on your Mac automatically now that the runner is online.

## 5) Quick Local Smoke (Optional)

```bash
docker compose up -d postgres redis
make start-paper
sleep 10 && curl -fsS :8000/ready | jq
make burnin-check
make paper-e2e
```

## 6) Common Snags & Fixes

- **Port 8000 in use**
  ```bash
  lsof -i :8000  # then kill, or
  PORT=8010 make start-paper
  ```

- **Docker not running**
  ```bash
  open -a Docker  # or: colima start
  ```

- **Runner not auto-starting** (mac reboots)
  ```bash
  cd ~/actions-runner && ./svc.sh status && ./svc.sh start
  ```

- **Mac sleeps**
  Keep power adapter connected and optionally run:
  ```bash
  caffeinate -dimsu &
  ```

## 7) Verify It's Truly Your Self-Hosted Box

In a running job → **View logs** → you'll see your machine name/runner name at the top.

On your Mac, you'll see containers in `docker ps` and fresh logs in `logs/` while the job runs.

## Makefile Commands

```bash
make runner-setup    # One-time setup
make runner-status   # Check if running
make runner-logs     # View logs
make runner-verify   # Comprehensive verification
```

---

**If you want a pre-filled runner registration command, share `<OWNER>/<REPO>` and I'll give you a paste-ready block.**


