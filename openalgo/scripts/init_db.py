import sys
import os

# Set cwd to project root
app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
os.chdir(app_root)
sys.path.append(app_root)

try:
    from database.auth_db import init_db
    print(f"Initializing database in {app_root}...")
    init_db()
    print("Database initialized.")
except Exception as e:
    print(f"Error initializing database: {e}")
    sys.exit(1)
