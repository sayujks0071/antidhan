import os
import sys
import requests
import logging
import logging.handlers
import socket
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load env vars
REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

# Config
OPENALGO_PORT = int(os.getenv('FLASK_PORT', 5000))
LOKI_PORT = 3100
GRAFANA_PORT = 3000
REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = REPO_ROOT / "logs" / "openalgo.log"
HEALTH_LOG_FILE = REPO_ROOT / "logs" / "healthcheck.log"
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Setup logging for healthcheck
logger = logging.getLogger("HealthCheck")
logger.setLevel(logging.INFO)
# Clear handlers
logger.handlers = []

# Create logs directory if it doesn't exist
HEALTH_LOG_FILE.parent.mkdir(exist_ok=True)

# File handler
handler = logging.handlers.RotatingFileHandler(HEALTH_LOG_FILE, maxBytes=1024*1024, backupCount=3)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
# Console handler
console = logging.StreamHandler()
console.setFormatter(formatter)
logger.addHandler(console)

def check_port(port, host='127.0.0.1'):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0

def check_url(url):
    try:
        response = requests.get(url, timeout=2)
        return response.status_code == 200
    except:
        return False

def analyze_logs(minutes=5):
    if not LOG_FILE.exists():
        return 0, []

    errors = []
    error_count = 0

    now = datetime.now()
    cutoff = now - timedelta(minutes=minutes)

    try:
        # Read last 2000 lines using tail
        try:
            output = subprocess.check_output(['tail', '-n', '2000', str(LOG_FILE)], stderr=subprocess.STDOUT)
            lines = output.decode('utf-8', errors='ignore').splitlines()
        except subprocess.CalledProcessError:
            return 0, []
        except FileNotFoundError:
            return 0, []

        for line in lines:
            if "ERROR" in line or "CRITICAL" in line:
                # Check timestamp
                # Expected format: [YYYY-MM-DD HH:MM:SS
                match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if match:
                    ts_str = match.group(1)
                    try:
                        ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                        if ts > cutoff:
                            error_count += 1
                            if len(errors) < 5: # Keep first 5 errors
                                errors.append(line)
                    except ValueError:
                        pass
    except Exception as e:
        logger.error(f"Failed to analyze logs: {e}")

    return error_count, errors

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")

def main():
    logger.info("Starting health check...")

    # 1. Check Services
    oa_up = check_port(OPENALGO_PORT)
    loki_up = check_url(f"http://localhost:{LOKI_PORT}/ready")
    grafana_up = check_port(GRAFANA_PORT)

    status_msg = []
    alert_needed = False

    if oa_up:
        status_msg.append("✅ OpenAlgo: UP")
    else:
        status_msg.append("🔴 OpenAlgo: DOWN")

    if loki_up:
        status_msg.append("✅ Loki: UP")
    else:
        status_msg.append("🔴 Loki: DOWN")

    if grafana_up:
        status_msg.append("✅ Grafana: UP")
    else:
        status_msg.append("🔴 Grafana: DOWN")

    logger.info(", ".join(status_msg))

    # 2. Analyze Logs
    err_count, sample_errors = analyze_logs(minutes=5)

    if err_count > 0:
        logger.warning(f"Found {err_count} errors in last 5 minutes.")
        status_msg.append(f"⚠️ {err_count} Recent Errors")

        if err_count > 10: # Threshold for alert
            alert_needed = True

        # Check for critical keywords
        for err in sample_errors:
            if "auth failed" in err.lower() or "order rejected" in err.lower():
                alert_needed = True
                break
    else:
        status_msg.append("✅ No Recent Errors")

    # 3. Alerting
    if alert_needed and TELEGRAM_BOT_TOKEN:
        msg = f"*OpenAlgo Health Alert*\n\n" + "\n".join(status_msg)
        if sample_errors:
            msg += "\n\n*Recent Errors:*\n`" + "\n".join(sample_errors[:3]) + "`"
        send_telegram(msg)
        logger.info("Alert sent.")

if __name__ == "__main__":
    main()
