#!/usr/bin/env python3
import sys
import os

# Determine app root and change working directory to it
app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if os.getcwd() != app_root:
    try:
        os.chdir(app_root)
    except Exception as e:
        print(f"Warning: Could not change working directory: {e}")

# Add openalgo directory to path
sys.path.append(app_root)

# Load environment variables
from utils.env_check import load_and_check_env_variables

# Wrap env check to handle potential exit
try:
    load_and_check_env_variables()
except SystemExit:
    print("Environment check failed. Please fix .env issues.")
    sys.exit(1)

from database.auth_db import init_db

if __name__ == "__main__":
    print("Initializing database...")
    try:
        init_db()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)
