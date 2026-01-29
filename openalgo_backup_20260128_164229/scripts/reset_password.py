#!/usr/bin/env python3
"""
Reset password for an existing OpenAlgo user
"""

import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from database.user_db import User, db_session, init_db

def reset_password(username, new_password):
    """Reset password for an existing user"""
    try:
        # Initialize database
        init_db()
        
        # Find the user
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"❌ User '{username}' not found!")
            return False
        
        # Reset the password
        print(f"Resetting password for user '{username}'...")
        user.set_password(new_password)
        db_session.commit()
        
        print(f"✅ Password reset successfully for user '{username}'!")
        print(f"\n📋 Login Credentials:")
        print(f"   Username: {username}")
        print(f"   Password: {new_password}")
        print(f"\n🔑 You can now login at: http://127.0.0.1:5001/auth/login")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db_session.rollback()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 reset_password.py <username> <new_password>")
        print("\nExample:")
        print("  python3 reset_password.py sayujks00712 Apollo@20417")
        sys.exit(1)
    
    username = sys.argv[1]
    new_password = sys.argv[2]
    
    success = reset_password(username, new_password)
    sys.exit(0 if success else 1)
