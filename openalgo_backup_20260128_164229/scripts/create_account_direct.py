#!/usr/bin/env python3
"""
Direct account creation script - bypasses web form
Creates an OpenAlgo admin account directly in the database
"""

import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from database.user_db import add_user, find_user_by_username, init_db, User, db_session
from database.auth_db import upsert_api_key
import secrets

def create_account(username, email, password):
    """Create an admin account directly"""
    try:
        # Initialize database
        init_db()
        
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"❌ User '{username}' already exists!")
            return False
        
        # Create the user
        print(f"Creating account for '{username}'...")
        user = add_user(username, email, password, is_admin=True)
        
        if user:
            print(f"✅ User '{username}' created successfully!")
            
            # Generate API key
            print("Generating API key...")
            api_key = secrets.token_hex(32)  # Generate 32 bytes = 64 hex chars
            key_id = upsert_api_key(username, api_key)
            
            if key_id:
                print(f"✅ API key generated successfully!")
                print(f"\n📋 Account Details:")
                print(f"   Username: {username}")
                print(f"   Email: {email}")
                print(f"   API Key: {api_key}")
                print(f"\n🔑 You can now login at: http://127.0.0.1:5002/auth/login")
                return True
            else:
                print("⚠️  User created but API key generation failed")
                return False
        else:
            print("❌ Failed to create user")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 create_account_direct.py <username> <email> <password>")
        print("\nExample:")
        print("  python3 create_account_direct.py sayujks0071 user@example.com Apollo@20417")
        sys.exit(1)
    
    username = sys.argv[1]
    email = sys.argv[2]
    password = sys.argv[3]
    
    success = create_account(username, email, password)
    sys.exit(0 if success else 1)
