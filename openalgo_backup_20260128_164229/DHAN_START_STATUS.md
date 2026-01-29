# Dhan OpenAlgo Start Status
**Date**: January 28, 2026, 12:30 IST

---

## ✅ OpenAlgo Started on Port 5002

**Process ID**: 66410  
**Port**: 5002  
**Log File**: `log/dhan_openalgo.log`  
**Web UI**: http://127.0.0.1:5002

---

## 🔍 Status Check

### Check if Running
```bash
curl http://127.0.0.1:5002/api/v1/ping
```

### Check Process
```bash
ps aux | grep 66410
```

### Check Port
```bash
lsof -i :5002
```

### View Logs
```bash
tail -f log/dhan_openalgo.log
```

---

## 🚀 Next Steps

1. **Wait for startup** (usually 10-30 seconds)
2. **Access Web UI**: http://127.0.0.1:5002
3. **Login to Dhan**: Broker Login → Dhan
4. **Start Option Strategies**: Via Web UI or script

---

## 🐛 Troubleshooting

### If Connection Refused

1. **Check if process is running**:
   ```bash
   ps aux | grep 66410
   ```

2. **Check logs for errors**:
   ```bash
   tail -50 log/dhan_openalgo.log
   ```

3. **Restart if needed**:
   ```bash
   kill 66410
   ./scripts/start_dhan_openalgo_background.sh
   ```

### Common Issues

- **Port conflict**: Another process using port 5002
- **Missing dependencies**: Check Python packages
- **Database error**: Check database file permissions
- **Environment variables**: Verify `.env.dhan` is loaded

---

**Status**: ✅ Started, waiting for full initialization
