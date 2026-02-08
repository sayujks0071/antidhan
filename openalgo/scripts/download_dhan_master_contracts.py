import sys
import os
import logging
import sqlite3
from dotenv import load_dotenv

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Add openalgo directory to path to support internal imports like 'from database...'
openalgo_dir = os.path.join(repo_root, 'openalgo')
if openalgo_dir not in sys.path:
    sys.path.insert(0, openalgo_dir)

# Load environment variables
load_dotenv(os.path.join(openalgo_dir, '.env'))

# Set environment variable for database if not set
if not os.getenv("DATABASE_URL"):
    # Use absolute path to avoid confusion
    db_path = os.path.join(openalgo_dir, "db", "openalgo.db")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

# Check for critical env vars
if not os.getenv("API_KEY_PEPPER"):
    # Don't crash, but warn. For script execution, we might need it.
    # However, for downloading contracts, maybe it's not strictly needed?
    # master_contract_db imports auth_db which checks it.
    print("Warning: API_KEY_PEPPER not set in environment.")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure tmp directory exists
os.makedirs("tmp", exist_ok=True)

# Mock socketio
class MockSocketIO:
    def __init__(self, *args, **kwargs):
        self.server = None # Mock server attribute if accessed
    def emit(self, event, data, **kwargs):
        logger.info(f"SocketIO emit: {event} - {data}")
    def init_app(self, app):
        pass
    def run(self, app, *args, **kwargs):
        pass

# Patch both openalgo.extensions and extensions (if imported directly)
import openalgo.extensions
openalgo.extensions.socketio = MockSocketIO()

# Also try to import extensions directly and patch it, because master_contract_db uses 'from extensions'
try:
    import extensions
    extensions.socketio = MockSocketIO()
    sys.modules['extensions'] = extensions # Ensure future imports get this
except ImportError:
    pass

try:
    from openalgo.broker.dhan.database.master_contract_db import init_db, master_contract_download, SymToken, db_session

    logger.info("Initializing Master Contract Database...")
    # Ensure the directory exists
    db_dir = os.path.join(openalgo_dir, "db")
    os.makedirs(db_dir, exist_ok=True)

    init_db()

    logger.info("Downloading Dhan Master Contracts...")
    master_contract_download()
    logger.info("Download complete.")

    # Verify by counting rows
    count = db_session.query(SymToken).count()
    logger.info(f"SymToken table now has {count} rows.")

except Exception as e:
    logger.error(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
