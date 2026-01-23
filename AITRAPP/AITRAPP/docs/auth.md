# Kite Authentication Guide

This document outlines the daily authentication process for the AITRAPP trading system using Zerodha Kite Connect.

## Overview

Kite Connect requires a valid `access_token` to interact with the API. This token expires daily.
Due to Zerodha's security policies and [Kite Trade guidelines](https://kite.trade/docs/connect/v3/exceptions/), automated login (using Selenium/headless browsers) is **strictly prohibited**.

Therefore, we implement a **Daily Manual Login Flow** facilitated by a bootstrap script.

## Daily Schedule (8:00 AM IST)

The system is designed to be bootstrapped every morning at 08:00 AM IST.

### Automation vs Manual Action

1.  **Automation**: The `kite_auth_bootstrap.py` script runs automatically via cron or CI.
2.  **Manual Action**: The user must click the generated login URL and complete the 2FA process on Zerodha's website.
3.  **Automation**: The script captures the callback, exchanges the token, and updates the secure storage.

## Setup

### 1. Environment Variables

Ensure your `.env` file contains your Kite API credentials:

```env
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
KITE_USER_ID=your_user_id
APP_MODE=PAPER  # Default to PAPER for safety
```

### 2. Redirect URI

For the bootstrap script to work locally, set your Kite Connect App's **Redirect URI** to:
`http://localhost:8000/auth/kite/callback`

If you are running the API server in production, point it to your domain:
`https://your-domain.com/auth/kite/callback`

## Usage

### Local / VPS (Interactive)

Run the bootstrap script:

```bash
python scripts/kite_auth_bootstrap.py
```

1.  The script checks if the current session is valid.
2.  If invalid, it starts a local server on port 8000.
3.  It prints a Login URL.
4.  Open the URL in your browser, log in to Zerodha.
5.  The browser redirects to `localhost:8000`, the script captures the token, saves it to `.env`, and exits.

### Cron Job (Example)

To automate the check (and prompt if needed):

```bash
# Run at 8:00 AM daily
0 8 * * * cd /path/to/repo && TRADING_MODE=paper /usr/bin/python3 scripts/kite_auth_bootstrap.py >> /var/log/kite_auth.log 2>&1
```

*Note: Since the login is manual, the cron job will hang waiting for the callback if the session is invalid. It is recommended to run this in a terminal or use a notification system to alert you to login.*

### CI / GitHub Actions

In CI environments, we cannot perform interactive login. The workflow should check for validity and alert if action is needed.

```bash
python scripts/kite_auth_bootstrap.py --check-only
```

If this command exits with status `1` (invalid session), the CI pipeline can trigger an alert (Email, Slack, GitHub Issue) containing the login URL.

## Security

*   **No Password Storage**: We never store Zerodha passwords or TOTP secrets.
*   **Token Storage**: `access_token` is stored in the `.env` file (local) or injected via secrets manager (cloud).
*   **Logs**: The bootstrap script masks sensitive tokens in logs.
*   **Live Safety**: `APP_MODE` defaults to `PAPER`. Live trading requires explicit configuration.
*   **Order Blocking**: The execution engine explicitly blocks order placement in LIVE mode if a valid `access_token` is not present, preventing accidental unauthorized trading attempts.
