# Dhan Login - Step by Step Guide
**Date**: January 28, 2026

---

## 🔴 Important: Login Order Matters!

**You MUST login to OpenAlgo Web UI FIRST, then login to Dhan broker.**

---

## 📋 Step-by-Step Instructions

### Step 1: Login to OpenAlgo Web UI

1. **Open**: http://127.0.0.1:5002
2. **You should see**: Login page
3. **Enter credentials**:
   - **Username**: `sayujks0071`
   - **Password**: `Apollo@20417`
4. **Click**: "Login" button
5. **Verify**: You see the OpenAlgo dashboard/homepage

**⚠️ If you skip this step, Dhan login will redirect you back to login!**

---

### Step 2: Navigate to Broker Login

1. **In the OpenAlgo Web UI** (after Step 1):
2. **Click**: "Broker Login" (in the navigation menu)
   - Usually at the top or in a menu
3. **You should see**: List of brokers (Kite, Dhan, etc.)

---

### Step 3: Login to Dhan

1. **Find**: "Dhan" in the broker list
2. **Click**: "Login with Dhan" button
3. **You'll be redirected** to Dhan's OAuth page
4. **Authorize** the application on Dhan's page
5. **You'll be redirected back** to OpenAlgo
6. **Verify**: Broker Status shows Dhan as "Connected" ✅

---

## 🔍 What's Happening Behind the Scenes

1. **OpenAlgo checks**: Are you logged in? (Session check)
2. **If not logged in**: Redirects to `/auth/login` ❌
3. **If logged in**: Proceeds to Dhan OAuth ✅
4. **Dhan OAuth flow**:
   - Generates consent with Client ID
   - Redirects to Dhan login page
   - User authorizes
   - Dhan redirects back with token
   - OpenAlgo validates and stores token

---

## ✅ Verification

After completing all steps, verify:

1. **Broker Status**: Shows "Connected" for Dhan
2. **No errors**: Check for error messages
3. **Can access**: Option strategies should work

---

## 🐛 Common Mistakes

### ❌ Mistake 1: Trying Dhan login without OpenAlgo login
- **Symptom**: Redirects to login page
- **Fix**: Login to OpenAlgo first (Step 1)

### ❌ Mistake 2: Using wrong port
- **Symptom**: Can't access Web UI
- **Fix**: Use http://127.0.0.1:5002 (not 5001)

### ❌ Mistake 3: Session expired
- **Symptom**: Was logged in, now redirects to login
- **Fix**: Login to OpenAlgo again, then try Dhan

---

## 📝 Quick Checklist

- [ ] Port 5002 is running
- [ ] Open http://127.0.0.1:5002
- [ ] Login to OpenAlgo (sayujks0071 / Apollo@20417)
- [ ] See OpenAlgo dashboard
- [ ] Click "Broker Login"
- [ ] Click "Login with Dhan"
- [ ] Authorize on Dhan page
- [ ] Redirected back to OpenAlgo
- [ ] See "Connected" status

---

## 🚀 After Successful Login

Once Dhan is connected:

1. **Start Option Strategy**:
   ```bash
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   ./scripts/start_option_strategy_port5002.sh
   ```

2. **Monitor**: Check logs for option data
3. **Trade**: Option strategies can now place orders

---

**Status**: ✅ Ready to login - follow steps above!
