# Create OpenAlgo Account on Port 5002

## ✅ Setup Page is Accessible

The setup page is available and ready for account creation.

## Step-by-Step Instructions

### Step 1: Open Setup Page

Open your browser and navigate to:
```
http://127.0.0.1:5002/setup
```

### Step 2: Fill Out the Form

Enter the following information:

- **Username**: `sayujks0071` (or your preferred username)
- **Email**: Your email address (optional but recommended)
- **Password**: `Apollo@20417` (or your preferred strong password)

**Password Requirements:**
- Minimum 8 characters
- Must contain at least one uppercase letter
- Must contain at least one lowercase letter
- Must contain at least one number
- Must contain at least one special character

### Step 3: Submit the Form

Click the **"Create Account"** button.

### Step 4: Account Created

After successful account creation:
1. You'll see a success message
2. A TOTP QR code will be displayed (save this for password recovery)
3. An API key will be automatically generated
4. You'll be redirected to the login page

### Step 5: Login

1. Go to: `http://127.0.0.1:5002/auth/login`
2. Enter your credentials:
   - Username: `sayujks0071`
   - Password: `Apollo@20417`
3. Click "Login"

### Step 6: Get Your API Key

After logging in:
1. Navigate to: `http://127.0.0.1:5002/apikey`
   OR
   Go to: Settings → API Keys
2. Your API key should already be generated (created during setup)
3. Copy the API key for use in strategies

## Troubleshooting

### Setup Page Redirects to Login?

If `/setup` redirects to `/auth/login`, it means a user already exists. In this case:
- Use the existing credentials to login
- Or check the database to see which users exist

### Password Validation Error?

Make sure your password meets all requirements:
- At least 8 characters
- Contains uppercase, lowercase, number, and special character

### Still Having Issues?

Check the OpenAlgo logs:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
tail -f log/openalgo.log
```

Or check the port 5002 specific log:
```bash
tail -f dhan_port5002.log
```
