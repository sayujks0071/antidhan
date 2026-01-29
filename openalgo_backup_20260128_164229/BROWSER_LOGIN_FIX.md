# Browser Login Troubleshooting - Quick Fix Guide

## 🔍 Current Status

- ✅ **Server Running**: Port 5002 is active
- ✅ **Login Page Accessible**: http://127.0.0.1:5002/auth/login loads
- ⚠️ **Login Issue**: Unable to login via browser

---

## 🚀 Quick Fix Steps

### Step 1: Clear Browser Cache & Cookies

**Chrome/Edge:**
1. Press `Cmd + Shift + Delete` (Mac) or `Ctrl + Shift + Delete` (Windows)
2. Select:
   - ✅ Cookies and other site data
   - ✅ Cached images and files
3. Time range: **All time**
4. Click **Clear data**

**Safari:**
1. Safari → Preferences → Privacy
2. Click **Manage Website Data**
3. Search for `127.0.0.1`
4. Click **Remove** → **Remove Now**

**Firefox:**
1. Press `Cmd + Shift + Delete`
2. Select Cookies and Cache
3. Click **Clear Now**

### Step 2: Try Incognito/Private Mode

1. Open a new **Incognito/Private** window
2. Navigate to: `http://127.0.0.1:5002/auth/login`
3. Try logging in with:
   - **Username**: `sayujks0071`
   - **Password**: `Apollo@20417`

### Step 3: Check Browser Console for Errors

1. Open **Developer Tools**: `F12` or `Cmd + Option + I` (Mac)
2. Go to **Console** tab
3. Try to login
4. Look for **red error messages**
5. Share any errors you see

### Step 4: Check Network Tab

1. Open **Developer Tools** → **Network** tab
2. Try to login
3. Find the `/auth/login` request
4. Check:
   - **Status Code**: Should be 200 (not 403, 400, or 500)
   - **Response**: Should show `{"status": "success"}`
   - **Request**: Should include username, password, csrf_token

---

## 🔧 Common Issues & Solutions

### Issue 1: "Rate limit exceeded"

**Symptom**: Error message about rate limiting (5 attempts per minute)

**Solution**:
1. **Wait 1-2 minutes** before trying again
2. **Clear cookies** for `127.0.0.1:5002`
3. **Use incognito mode**

### Issue 2: "Invalid credentials"

**Symptom**: Login form says username/password is wrong

**Solution**:
- Double-check credentials:
  - Username: `sayujks0071` (no spaces)
  - Password: `Apollo@20417` (case-sensitive)
- Try copying/pasting instead of typing

### Issue 3: Login button does nothing

**Symptom**: Clicking login button doesn't submit form

**Solution**:
1. Check browser console for JavaScript errors
2. Try a different browser
3. Disable browser extensions temporarily
4. Check if JavaScript is enabled

### Issue 4: Page redirects immediately

**Symptom**: After login, page redirects back to login

**Solution**:
1. Check if cookies are enabled in browser
2. Try incognito mode
3. Check server logs for session errors

---

## 🧪 Test Login Programmatically

If browser login still doesn't work, test login via script:

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/test_login.py
```

This will show you the exact error message.

---

## 📋 Login Credentials

- **URL**: `http://127.0.0.1:5002/auth/login`
- **Username**: `sayujks0071`
- **Password**: `Apollo@20417`

---

## 🔄 Alternative: Create New Account

If login still fails, you might need to create a new account:

1. Navigate to: `http://127.0.0.1:5002/setup`
2. Create a new admin account
3. Use the new credentials to login

---

## ✅ Verification

After successful login, you should see:
- OpenAlgo dashboard/homepage
- Navigation menu with options
- No redirect back to login page

---

**Next Step**: Try Step 1 (Clear Cache) first, then Step 2 (Incognito mode). This fixes 90% of login issues!
