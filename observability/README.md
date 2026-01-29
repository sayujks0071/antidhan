# OpenAlgo Local Observability Stack

This directory contains the "local drain" observability stack for OpenAlgo, using Grafana Loki, Promtail, and Grafana.

## Components

1.  **Loki**: Log aggregation system (Port 3100).
2.  **Promtail**: Log shipper that tails `../logs/*.log` and sends them to Loki.
3.  **Grafana**: Visualization dashboard (Port 3000).

## Setup & Usage

### Prerequisites
- Docker and Docker Compose
- Python 3

### Quick Start

Use the `Makefile` in the repository root:

1.  **Start the Stack**:
    ```bash
    make obs-up
    ```
    This brings up Loki, Promtail, and Grafana in the background.

2.  **Access Grafana**:
    - URL: http://localhost:3000
    - User: `admin`
    - Password: `admin` (or as configured in `docker-compose.yml`)
    - Go to **Dashboards** > **OpenAlgo** folder > **OpenAlgo Dashboard**.

3.  **Run OpenAlgo**:
    ```bash
    make run
    ```
    Or run normally: `python3 -m openalgo.app`. Logs will be written to `logs/openalgo.log` and automatically shipped to Grafana.

4.  **Check Status**:
    ```bash
    make status
    ```

5.  **Stop Stack**:
    ```bash
    make obs-down
    ```

## Logging Configuration

Logging is configured in `openalgo_observability/logging_setup.py`.
- **Log File**: `logs/openalgo.log` (Rotates at 10MB, keeps 5 backups).
- **Format**: Text (default) or JSON (if `OPENALGO_LOG_JSON=1`).
- **Redaction**: Secrets (API keys, tokens) are redacted automatically.

### Environment Variables
- `OPENALGO_LOG_LEVEL`: Set log level (default: INFO).
- `OPENALGO_LOG_JSON`: Set to `1` for JSON logs.

## Monitoring & Alerts

### Health Check Script
Located at `scripts/healthcheck.py`. It checks:
- OpenAlgo port (5000)
- Loki/Grafana availability
- Recent errors in `logs/openalgo.log`

### Automated Monitoring
You can install a background scheduler (Systemd timer or Cron) to run the health check every 5 minutes:

```bash
make install-monitoring
```

This will log health status to `logs/healthcheck.log`.

### Telegram Alerts
To enable Telegram notifications for health issues:
1.  Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to your `.env` file.
2.  The health check script will send a message if:
    - Services are down.
    - Error rate spikes (>10 errors in 5 mins).
    - Critical errors ("auth failed", "order rejected") are found.

To uninstall monitoring:
```bash
make uninstall-monitoring
```
