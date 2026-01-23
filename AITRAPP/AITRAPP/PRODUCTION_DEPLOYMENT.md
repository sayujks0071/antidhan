# Production Deployment Guide

## 🔒 Lock Exact Working Runtime

### For Production Boxes

**Always install from `requirements.lock` for exact versions:**

```bash
# Production deployment
pip install -r requirements.lock

# Verify versions match
python -c "import fastapi, uvicorn; print(f'fastapi: {fastapi.__version__}, uvicorn: {uvicorn.__version__}')"
```

### Why Lock?

Your current runtime shows newer libs than earlier ranges. Freeze what's working now to avoid drift before LIVE.

### Update Lock

When you need to update dependencies:

```bash
# Update requirements.txt with new versions
# Then regenerate lock
pip install -r requirements.txt
pip freeze > requirements.lock

# Commit both files
git add requirements.txt requirements.lock
git commit -m "Update dependencies and lock versions"
```

## 📢 Alert Configuration

### Telegram Alerts

Set environment variables:

```bash
export TG_BOT_TOKEN="your_telegram_bot_token"
export TG_CHAT_ID="your_telegram_chat_id"
```

**Get Chat ID:**
1. Start a chat with your bot
2. Send a message
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Find `chat.id` in the response

### Slack Alerts

Set environment variable:

```bash
export SLACK_WEBHOOK_URL="your_slack_webhook_url"
```

**Create Webhook:**
1. Go to Slack Apps → Incoming Webhooks
2. Create new webhook
3. Copy webhook URL

### What Alerts On

- **Kill Switch**: When `/flatten` is triggered
  - Includes reason and position details
  - Sent via configured channels (Telegram/Slack)

### Test Alerts

```bash
# Trigger test alert
curl -X POST http://localhost:8000/flatten \
  -H 'Content-Type: application/json' \
  -d '{"reason":"test_alert"}'
```

## 🚀 Production Checklist

Before deploying to production:

- [ ] `requirements.lock` is committed
- [ ] Alert channels configured (Telegram/Slack)
- [ ] Test alerts working
- [ ] Database migrations applied
- [ ] Schema verified (details + enum)
- [ ] Pre-live gate passes
- [ ] Backup strategy in place
- [ ] Monitoring configured

## 📋 Deployment Steps

1. **Install locked dependencies:**
   ```bash
   pip install -r requirements.lock
   ```

2. **Apply migrations:**
   ```bash
   alembic upgrade head
   ```

3. **Verify schema:**
   ```bash
   make prelive-gate
   ```

4. **Start application:**
   ```bash
   make paper  # or make live
   ```

5. **Test alerts:**
   ```bash
   curl -X POST http://localhost:8000/flatten \
     -H 'Content-Type: application/json' \
     -d '{"reason":"deployment_test"}'
   ```

## 🔍 Monitoring

### Check Alert Configuration

```bash
# Check if alerts are enabled
python -c "from packages.core.alerts import alert_manager; print(f'Alerts enabled: {alert_manager.enabled}')"
```

### Verify Kill Switch Metric

```bash
curl -s :8000/metrics | grep trader_kill_switch_total
```

## ⚠️ Important Notes

1. **Always use `requirements.lock` in production** - ensures exact versions
2. **Test alerts before LIVE** - verify Telegram/Slack integration works
3. **Monitor kill switch usage** - alerts help catch unexpected flattens
4. **Keep lock file in version control** - ensures reproducibility

