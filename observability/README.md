# OpenAlgo Local Observability Stack

This directory contains the configuration for running a local observability stack using Grafana, Loki, and Promtail.

## Components

1.  **Loki**: Log aggregation system (Port 3100).
2.  **Promtail**: Log collector that tails logs from `../logs/*.log` and ships them to Loki.
3.  **Grafana**: Visualization dashboard (Port 3000).

## Setup

### Prerequisites
- Docker and Docker Compose installed.
- Python 3 for running OpenAlgo.

### Quick Start

Use the `Makefile` in the repo root:

```bash
# Start Observability Stack
make obs-up

# Check Status
make status

# View Logs (Tail)
make obs-logs

# Stop Stack
make obs-down
```

### Accessing Dashboards

1.  Open [http://localhost:3000](http://localhost:3000).
2.  Login with `admin` / `admin`.
3.  Navigate to **Dashboards > Manage**.
4.  You should see **OpenAlgo Local Dashboard**.

### Logging Configuration

OpenAlgo uses a custom logging module `openalgo_observability` that:
- Writes to `logs/openalgo.log`.
- Redacts sensitive keys (api_key, password, etc.).
- Supports JSON logging via `OPENALGO_LOG_JSON=1`.

To run OpenAlgo with logging enabled:

```bash
# Run the daily startup script
make run

# Or manually
python3 daily_startup.py
```

### Alerts

A health check script is provided in `scripts/healthcheck.py`. It runs periodically to:
1.  Check if OpenAlgo and Observability services are up.
2.  Query Loki for error spikes or critical failures.
3.  Send alerts to Console/Desktop/Telegram.

To enable Telegram alerts, set environment variables:
```bash
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

To install the scheduled health check:
```bash
# Install as Systemd User Timer (Recommended)
./scripts/install_systemd_user_timers.sh

# Or Install as Cron job
./scripts/install_cron.sh
```
