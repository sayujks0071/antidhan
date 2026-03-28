#!/usr/bin/env python3
"""
Dhan Login Assistant
--------------------
Interactive tool to update Dhan Authentication Tokens.
1. Asks for Client ID and Access Token.
2. Updates .env file.
3. Updates Database.
4. Verifies Connectivity instantly.
"""

import os
import sys
import requests

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    from database.auth_db import upsert_auth, db_session
except ImportError:
    print("Error: Could not import database modules. Run from project root.")
    sys.exit(1)

# ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    clear_screen()
    print(f"{CYAN}========================================{RESET}")
    print(f"{CYAN}       OpenAlgo Dhan Login Assistant    {RESET}")
    print(f"{CYAN}========================================{RESET}")
    print("")


def update_env_file(client_id, access_token):
    env_path = os.path.join(project_root, ".env")
    try:
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()
        else:
            lines = []

        new_lines = []
        key_found = False
        new_key_line = f"BROKER_API_KEY='{client_id}:::{access_token}'\n"

        for line in lines:
            if line.strip().startswith("BROKER_API_KEY"):
                new_lines.append(new_key_line)
                key_found = True
            else:
                new_lines.append(line)

        if not key_found:
            new_lines.append("\n" + new_key_line)

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        print(f"{GREEN}[SUCCESS] Updated .env file.{RESET}")
        return True
    except Exception as e:
        print(f"{RED}[ERROR] Failed to update .env: {e}{RESET}")
        return False


def check_connection(client_id, access_token):
    print(f"\n{YELLOW}Verifying Connection with Dhan...{RESET}")
    try:
        headers = {
            "access-token": access_token,
            "client-id": client_id,
            "Content-Type": "application/json",
        }
        # Fetch Fund Limit as a test
        resp = requests.get(
            "https://api.dhan.co/fund-limits", headers=headers, timeout=5
        )

        if resp.status_code == 200:
            data = resp.json()
            print(f"{GREEN}[SUCCESS] Connection Verified!{RESET}")
            print(
                f"Funds Available: {data.get('data', {}).get('availabelBalance', 'Unknown')}"
            )
            return True
        elif resp.status_code == 401:
            print(
                f"{RED}[ERROR] Authentication Failed. Token is invalid or expired.{RESET}"
            )
        else:
            print(f"{RED}[ERROR] API Error: {resp.status_code} - {resp.text}{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Connection Exception: {e}{RESET}")
    return False


def main():
    print_header()

    # 1. Get Inputs
    client_id = input(f"{YELLOW}Enter Dhan Client ID (e.g., 10000001): {RESET}").strip()
    if not client_id:
        print(f"{RED}Client ID is required.{RESET}")
        return

    print(f"\n{YELLOW}Tip: Generate a new Access Token from web.dhan.co > APIs{RESET}")
    access_token = input(f"{YELLOW}Enter Dhan Access Token (JWT): {RESET}").strip()
    if not access_token:
        print(f"{RED}Access Token is required.{RESET}")
        return

    # 2. Update .env
    print("")
    update_env_file(client_id, access_token)

    # 3. Update Database
    username = (
        input(f"\n{YELLOW}Enter Strategy Username (default: sks20417): {RESET}").strip()
        or "sks20417"
    )
    try:
        upsert_auth(
            name=username,
            auth_token=access_token,
            broker="dhan",
            feed_token=access_token,
            user_id=client_id,
            revoke=False,
        )
        print(f"{GREEN}[SUCCESS] Database updated for user '{username}'.{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Database Update Failed: {e}{RESET}")

    # 4. Verify
    if check_connection(client_id, access_token):
        print(f"\n{GREEN}Login Flow Completed Successfully!{RESET}")
        print("You can now restart the server: `python3 scripts/start_server.py`")
    else:
        print(
            f"\n{RED}Login Verification Failed. Please check your token and try again.{RESET}"
        )


if __name__ == "__main__":
    main()
