# Browser Login Troubleshooting Guide

## ✅ Account Created Successfully

Your account has been created:
- **Username**: `sayujks0071`
- **Password**: `Apollo@20417`
- **API Key**: `5e1da831bafa12ceea9eef7fb8562087656f84c347160fcb95b0e6982403caba`

## Common Browser Issues & Solutions

### Issue 1: Login Button Not Working / Form Not Submitting

**Possible Causes:**
1. JavaScript errors in browser console
2. CSRF token expired or invalid
3. Browser cache/cookies issue
4. Network/CORS issues

**Solutions:**

#### Step 1: Check Browser Console
1. Open browser Developer Tools (F12 or Cmd+Option+I on Mac)
2. Go to "Console" tab
3. Try to login
4. Look for any red error messages
5. Share the error messages if you see any

#### Step 2: Clear Browser Cache & Cookies
1. **Chrome/Edge**: 
   - Press `Cmd+Shift+Delete` (Mac) or `Ctrl+Shift+Delete` (Windows)
   - Select "Cookies and other site data" and "Cached images and files"
   - Time range: "All time"
   - Click "Clear data"

2. **Firefox**:
   - Press `Cmd+Shift+Delete` (Mac) or `Ctrl+Shift+Delete` (Windows)
   - Select "Cookies" and "Cache"
   - Click "Clear Now"

3. **Safari**:
   - Safari → Preferences → Privacy → Manage Website Data
   - Remove all data for `127.0.0.1`

#### Step 3: Try Incognito/Private Mode
1. Open a new incognito/private window
2. Navigate to: `http://127.0.0.1:5002/auth/login`
3. Try logging in

#### Step 4: Try Different Browser
- If using Chrome, try Firefox or Safari
- If using Safari, try Chrome

#### Step 5: Check Network Tab
1. Open Developer Tools (F12)
2. Go to "Network" tab
3. Try to login
4. Look for the `/auth/login` request
5. Check:
   - Status code (should be 200)
   - Response (should be JSON with `{"status": "success"}`)
   - Request payload (should include username, password, csrf_token)

### Issue 2: "Invalid credentials" Error

**Solution:**
- Double-check username: `sayujks0071`
- Double-check password: `Apollo@20417`
- Make sure there are no extra spaces

### Issue 3: Page Not Loading / Connection Refused

**Solution:**
1. Check if server is running:
   ```bash
   lsof -ti:5002
   ```
   Should return a process ID

2. If not running, start it:
   ```bash
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   ./scripts/start_dhan_port5002_final.sh
   ```

### Issue 4: CSRF Token Error

**Solution:**
1. Refresh the login page (F5 or Cmd+R)
2. Try logging in immediately after refresh
3. Make sure you're not opening the page in multiple tabs

## Quick Test

Run this command to test if login works programmatically:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/test_login.py
```

If this works but browser doesn't, it's likely a browser/JavaScript issue.

## Alternative: Direct Database Access

If browser login continues to fail, you can verify the account exists:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 -c "
from database.user_db import User, db_session
user = User.query.filter_by(username='sayujks0071').first()
if user:
    print(f'✅ User exists: {user.username}')
    print(f'   Email: {user.email}')
    print(f'   Admin: {user.is_admin}')
else:
    print('❌ User not found')
"
```

## Still Not Working?

Please provide:
1. **Browser name and version** (e.g., Chrome 120, Safari 17)
2. **Error messages from browser console** (F12 → Console tab)
3. **Network request details** (F12 → Network tab → click on `/auth/login` request)
4. **What happens when you click login** (nothing? error message? page reload?)
