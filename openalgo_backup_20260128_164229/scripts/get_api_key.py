#!/usr/bin/env python3
"""
Get OpenAlgo API Key from database
"""
import sqlite3
import os
import sys

def get_api_key():
    """Get the first available API key from database"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'openalgo.db')
    
    if not os.path.exists(db_path):
        print("❌ Database not found. Please generate an API key via Web UI first.")
        print("   Go to: http://127.0.0.1:5001 → API Keys")
        return None
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get first API key
        cursor.execute('SELECT api_key, username FROM api_keys LIMIT 1')
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            api_key, username = row
            print(f"✅ Found API Key for user: {username}")
            print(f"   API Key: {api_key}")
            return api_key
        else:
            print("❌ No API keys found in database.")
            print("   Please generate one via Web UI: http://127.0.0.1:5001 → API Keys")
            return None
            
    except Exception as e:
        print(f"❌ Error accessing database: {e}")
        return None

if __name__ == "__main__":
    api_key = get_api_key()
    if api_key:
        sys.exit(0)
    else:
        sys.exit(1)
