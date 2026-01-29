# Fix Login Rate Limit Issue

## 🔴 Problem Identified

**Error**: `429 - Rate limit exceeded`

**Cause**: Too many login attempts (limit is 5 attempts per minute)

---

## ✅ Solution

### Step 1: Wait for Rate Limit to Clear

**Wait 1-2 minutes** before trying to login again.

The rate limit resets after **1 minute** from your last failed attempt.

### Step 2: Clear Browser Cookies

While waiting, clear cookies for `127.0.0.1:5002`:

**Chrome/Edge:**
1. Press `Cmd + Shift + Delete`
2. Select "Cookies and other site data"
3. Time range: "All time"
4. Click "Clear data"

**Safari:**
1. Safari → Preferences → Privacy
2. Click "Manage Website Data"
3. Search for `127.0.0.1`
4. Click "Remove"

### Step 3: Try Login Again (After 1-2 Minutes)

1. Open browser (or use incognito mode)
2. Navigate to: `http://127.0.0.1:5002/auth/login`
3. Enter credentials:
   - **Username**: `sayujks0071`
   - **Password**: `Apollo@20417`
4. Click "Login"

---

## 🚀 Quick Fix Script

Run this to check when rate limit clears:

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/test_login.py
```

This will tell you if rate limit is still active.

---

## 💡 Prevention Tips

1. **Don't spam the login button** - Wait between attempts
2. **Use password manager** - Avoid typos that cause failed attempts
3. **Clear cookies** - If you see rate limit, clear cookies and wait
4. **Use incognito mode** - Fresh session, no cached rate limit state

---

## ⏰ Current Status

- ✅ Server is running on port 5002
- ✅ Login page is accessible
- ⚠️ **Rate limit active** - Wait 1-2 minutes before retrying

---

**Next Step**: Wait 1-2 minutes, then try logging in again!
