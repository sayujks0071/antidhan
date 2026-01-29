# Dhan Login Troubleshooting Guide
**Date**: January 28, 2026

---

## 🔴 Problem: Not Able to Login to Dhan

---

## ✅ Step-by-Step Login Process

### Step 1: Login to OpenAlgo Web UI First

**IMPORTANT**: You must be logged into OpenAlgo before you can login to Dhan broker.

1. **Open**: http://127.0.0.1:5002
2. **Login to OpenAlgo**:
   - Username: `sayujks0071`
   - Password: `Apollo@20417`
3. **Verify**: You see the dashboard/homepage

### Step 2: Navigate to Broker Login

1. **Click**: "Broker Login" (in navigation menu)
2. **Select**: "Dhan" from the broker list
3. **Click**: "Login with Dhan" button

### Step 3: Complete OAuth Flow

1. You'll be redirected to Dhan's OAuth page
2. **Authorize** the application
3. You'll be redirected back to OpenAlgo
4. **Verify**: Broker Status shows "Connected"

---

## 🔍 Common Issues & Solutions

### Issue 1: "Redirecting to login" or Session Error

**Problem**: Not logged into OpenAlgo Web UI first.

**Solution**:
1. Go to http://127.0.0.1:5002
2. Login with OpenAlgo credentials first
3. Then try Dhan login again

### Issue 2: "Client ID not found" Error

**Problem**: BROKER_API_KEY not set correctly.

**Solution**: Verify BROKER_API_KEY format:
```bash
# Should be: client_id:::api_key
# Expected: 1105009139:::df1da5de
```

**Check**:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
ps e -p $(lsof -ti:5002) | grep BROKER_API_KEY
```

**Fix**: Restart port 5002 with correct environment:
```bash
./scripts/start_dhan_port5002_noenv.sh
```

### Issue 3: OAuth Redirect URL Mismatch

**Problem**: Redirect URL doesn't match Dhan app configuration.

**Solution**: Verify redirect URL in Dhan dashboard:
- Should be: `http://127.0.0.1:5002/dhan/callback`
- Must match exactly in Dhan app settings

### Issue 4: "Failed to generate consent"

**Problem**: API credentials invalid or app not approved.

**Solution**:
1. Verify credentials in Dhan dashboard:
   - Client ID: `1105009139`
   - API Key: `df1da5de`
   - API Secret: `fddc233a-a819-4e40-a282-1acbf9cd70b9`
2. Check if app is approved/active
3. Verify redirect URL matches

### Issue 5: Port 5002 Not Running

**Problem**: OpenAlgo not running on port 5002.

**Solution**:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./scripts/start_dhan_port5002_noenv.sh
```

---

## 🧪 Test Login Configuration

Run the test script:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./scripts/test_dhan_login.sh
```

This will check:
- Port 5002 accessibility
- BROKER_API_KEY format
- OAuth endpoint availability

---

## 📋 Complete Login Checklist

- [ ] Port 5002 is running (`lsof -i :5002`)
- [ ] Web UI accessible (http://127.0.0.1:5002)
- [ ] Logged into OpenAlgo Web UI
- [ ] BROKER_API_KEY set correctly (client_id:::api_key)
- [ ] Redirect URL matches Dhan app settings
- [ ] Dhan app is approved/active
- [ ] Click "Login with Dhan" button
- [ ] Complete OAuth authorization
- [ ] Verify "Connected" status

---

## 🔧 Quick Fixes

### Restart Port 5002 with Correct Config

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./scripts/start_dhan_port5002_noenv.sh
```

### Check Logs for Errors

```bash
tail -f log/dhan_port5002.log | grep -E "ERROR|dhan|oauth|consent"
```

### Verify Environment Variables

```bash
ps e -p $(lsof -ti:5002) | grep -E "BROKER_API_KEY|REDIRECT_URL"
```

---

## 📞 Still Having Issues?

1. **Check browser console** for JavaScript errors
2. **Check OpenAlgo logs**: `tail -f log/dhan_port5002.log`
3. **Verify Dhan app status** in Dhan dashboard
4. **Test OAuth endpoint**: http://127.0.0.1:5002/dhan/initiate-oauth

---

**Status**: ⚠️ Login troubleshooting guide created
