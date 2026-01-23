#!/usr/bin/env python3
"""Quick script to generate Kite Connect access token"""
import os
import re
import sys

from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Load environment variables
load_dotenv()

def main():
    print("=" * 60)
    print("Kite Connect Access Token Generator")
    print("=" * 60)

    # Get credentials from env or prompt
    api_key = os.getenv("KITE_API_KEY")
    api_secret = os.getenv("KITE_API_SECRET")

    if not api_key:
        print("\n❌ KITE_API_KEY not found in environment.")
        if sys.stdin.isatty():
             api_key = input("Enter KITE_API_KEY: ").strip()
        else:
             print("Please set it in .env or environment.")
             return

    if not api_secret:
        print("\n❌ KITE_API_SECRET not found in environment.")
        if sys.stdin.isatty():
             api_secret = input("Enter KITE_API_SECRET: ").strip()
        else:
             print("Please set it in .env or environment.")
             return

    print(f"\nAPI Key: {api_key}")

    # Check if token provided as argument
    if len(sys.argv) > 1:
        request_token = sys.argv[1].strip()
        print("\nUsing request_token from command line")
    else:
        print("\n📝 Steps:")
        print("1. Visit this URL in your browser:")
        print(f"   https://kite.trade/connect/login?api_key={api_key}&v=3")
        print("\n2. Login with your Zerodha credentials")
        print("\n3. After login, you'll be redirected to a URL like:")
        print("   http://localhost:8080/callback?request_token=XXXXX&action=login&status=success")
        print("\n4. Copy the 'request_token' value from the URL")
        print("\n   Then run:")
        print("   python get_kite_token.py YOUR_REQUEST_TOKEN")
        print("=" * 60)

        if sys.stdin.isatty():
            request_token = input("\nPaste the request_token here: ").strip()
        else:
            print("\n❌ No request token provided.")
            print("\nUsage: python get_kite_token.py YOUR_REQUEST_TOKEN")
            print("\nOr visit the URL above and login first.")
            return

    if not request_token:
        print("❌ No request token provided. Exiting.")
        return

    try:
        kite = KiteConnect(api_key=api_key)
        data = kite.generate_session(request_token, api_secret=api_secret)

        print("\n" + "=" * 60)
        print("✅ SUCCESS! Your credentials:")
        print("=" * 60)
        print(f"\nAccess Token: {data['access_token']}")
        print(f"User ID: {data['user_id']}")
        print("\n📋 Add these to your .env file:")
        print(f"KITE_ACCESS_TOKEN={data['access_token']}")
        print(f"KITE_USER_ID={data['user_id']}")
        print("\n" + "=" * 60)

        # Auto-update .env file
        env_file = os.path.join(os.path.dirname(__file__), '.env')

        # Read existing .env if it exists
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                content = f.read()
        else:
            content = ""

        # Update or append values
        if 'KITE_ACCESS_TOKEN=' in content:
            content = re.sub(r'KITE_ACCESS_TOKEN=.*', f"KITE_ACCESS_TOKEN={data['access_token']}", content)
        else:
            content += f"\nKITE_ACCESS_TOKEN={data['access_token']}"

        if 'KITE_USER_ID=' in content:
            content = re.sub(r'KITE_USER_ID=.*', f"KITE_USER_ID={data['user_id']}", content)
        else:
             content += f"\nKITE_USER_ID={data['user_id']}"

        # Also ensure API_KEY/SECRET are there if we entered them interactively
        if 'KITE_API_KEY=' not in content:
             content += f"\nKITE_API_KEY={api_key}"
        if 'KITE_API_SECRET=' not in content:
             content += f"\nKITE_API_SECRET={api_secret}"

        with open(env_file, 'w') as f:
            f.write(content)

        print("\n✅ .env file updated automatically!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("1. You copied the request_token correctly")
        print("2. You logged in within the last few minutes")
        print("3. The request_token hasn't expired")

if __name__ == "__main__":
    main()
