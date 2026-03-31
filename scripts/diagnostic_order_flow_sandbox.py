
import os
import sys
import json
import logging
from unittest.mock import patch, MagicMock
from flask import Flask, session

# Add both root and openalgo to sys.path to support various import styles
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Mock environment variables
os.environ['API_KEY_PEPPER'] = 'test_pepper' * 4
os.environ['BROKER_API_KEY'] = 'test_broker_key'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

# --- PATCH utils.session.check_session_validity BEFORE IMPORTS ---
mock_session_module = MagicMock()
def pass_through(f):
    return f
mock_session_module.check_session_validity = pass_through
sys.modules['utils.session'] = mock_session_module
sys.modules['openalgo.utils.session'] = mock_session_module

# --- PATCH DATABASE MODULES BEFORE IMPORTING APP CODE ---
# This ensures that when orders.py imports get_analyze_mode, it gets the mock.

patches = [
    patch('database.auth_db.get_auth_token', return_value='mock_token'),
    patch('database.auth_db.get_api_key_for_tradingview', return_value='mock_api_key'),
    patch('database.token_db.get_token', return_value='12345'),
    patch('database.token_db.get_br_symbol', return_value='SBIN'),
    patch('database.settings_db.get_analyze_mode', return_value=False),
    # Also patch openalgo.database.* just in case
    patch('openalgo.database.auth_db.get_auth_token', return_value='mock_token'),
    patch('openalgo.database.auth_db.get_api_key_for_tradingview', return_value='mock_api_key'),
    patch('openalgo.database.token_db.get_token', return_value='12345'),
    patch('openalgo.database.token_db.get_br_symbol', return_value='SBIN'),
    patch('openalgo.database.settings_db.get_analyze_mode', return_value=False),
]

active_patches = []
for p in patches:
    try:
        # We start the patch. If module not loaded, it might try to load it.
        # If it fails, we ignore.
        p.start()
        active_patches.append(p)
    except (ImportError, AttributeError):
        pass

# --- IMPORT APP CODE ---
try:
    # Use 'blueprints.orders' directly as that's how the app likely loads it
    # This ensures we share the same module instance and engine
    from blueprints.orders import orders_bp

    # Initialize DBs
    from database.auth_db import Base as AuthBase, engine as auth_engine
    from database.settings_db import Base as SettingsBase, engine as settings_engine
    from database.telegram_db import Base as TelegramBase, engine as telegram_engine
    from database.apilog_db import Base as ApiLogBase, engine as apilog_engine
    # database.token_db might use auth_db Base or its own? Let's assume its own if it has engine
    # Checking token_db imports... usually it shares nothing or uses sqlite.
    # We should import it to be safe.
    try:
        from database.token_db import Base as TokenBase, engine as token_engine
        TokenBase.metadata.create_all(token_engine)
    except ImportError:
        pass

    AuthBase.metadata.create_all(auth_engine)
    SettingsBase.metadata.create_all(settings_engine)
    TelegramBase.metadata.create_all(telegram_engine)
    ApiLogBase.metadata.create_all(apilog_engine)

except ImportError as e:
    logger.error(f"ImportError: {e}")
    sys.exit(1)

def create_app():
    app = Flask(__name__)
    app.secret_key = 'test_secret'
    app.register_blueprint(orders_bp)
    return app

def run_diagnostic():
    app = create_app()
    client = app.test_client()

    order_types = [
        {"type": "LIMIT", "price": "100", "trigger_price": "0"},
        {"type": "MARKET", "price": "0", "trigger_price": "0"},
        {"type": "SL", "price": "90", "trigger_price": "95"},
        {"type": "SL-M", "price": "0", "trigger_price": "95"},
    ]

    print("\n--- Starting Diagnostic Order Flow (Dhan Sandbox) ---\n")

    # Determine patches based on import_name
    # Since we imported 'openalgo.blueprints.orders', that is likely the module in sys.modules
    # But inside orders.py, it imports 'from database.settings_db ...'
    # So we need to patch 'openalgo.blueprints.orders.get_analyze_mode' ??
    # NO. 'from X import Y' creates a local name 'Y' in 'openalgo.blueprints.orders'.
    # We must patch THAT local name.

    patches_to_apply = [
        # Patch database modules directly as they are imported by blueprints and services
        ('database.auth_db.get_auth_token', 'mock_token'),
        ('database.auth_db.get_api_key_for_tradingview', 'mock_api_key'),
        ('database.token_db.get_token', '12345'),
        ('database.token_db.get_br_symbol', 'SBIN'),
        ('database.settings_db.get_analyze_mode', False),

        # Patch service layer dependencies (if they imported before patching)
        ('services.place_smart_order_service.get_token', '12345'),
        ('services.place_smart_order_service.get_analyze_mode', False),

        # Patch broker dependencies
        ('broker.dhan_sandbox.api.order_api.get_token', '12345'),
        ('broker.dhan_sandbox.api.order_api.get_br_symbol', 'SBIN'),
        ('broker.dhan_sandbox.api.order_api.get_open_position', '0'),
    ]

    active_patches = []

    # We patch request separately because we need the mock object
    request_patches = [
        'openalgo.broker.dhan_sandbox.api.order_api.request',
        'broker.dhan_sandbox.api.order_api.request'
    ]

    try:
        # Apply Value Patches
        for target, value in patches_to_apply:
            try:
                p = patch(target, return_value=value)
                p.start()
                active_patches.append(p)
                print(f"Patched {target}")
            except (ImportError, AttributeError) as e:
                print(f"Failed to patch {target}: {e}")

        # Apply Request Patches
        rejected_response_data = {
            "status": "failure",
            "remarks": "Market Closed",
            "orderStatus": "REJECTED",
            "orderId": "1001",
            "errorCode": "INVALID_MARKET_STATUS",
            "errorMessage": "Market is closed"
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(rejected_response_data)
        mock_resp.json.return_value = rejected_response_data

        for target in request_patches:
            try:
                p = patch(target, return_value=mock_resp)
                p.start()
                active_patches.append(p)
                print(f"Patched {target}")
            except (ImportError, AttributeError):
                pass

        for i, order in enumerate(order_types):
            print(f"Testing Order Type: {order['type']}")

            with client.session_transaction() as sess:
                sess['user'] = 'test_user'
                sess['broker'] = 'dhan_sandbox'

            payload = {
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "BUY",
                "pricetype": order['type'],
                "product": "MIS",
                "quantity": "1",
                "price": order['price'],
                "trigger_price": order['trigger_price'],
                "disclosed_quantity": "0",
                "position_size": "0",
                "strategy": "DIAGNOSTIC_TEST"
            }

            response = client.post('/placesmartorder', json=payload)

            print(f"Response Status Code: {response.status_code}")
            print(f"Response Data: {response.get_json()}")

            data = response.get_json()

            if response.status_code == 500:
                print(f"FAILED: Server Error for {order['type']}")
                # sys.exit(1)

            if data and (data.get('status') == 'failure' or data.get('orderStatus') == 'REJECTED'):
                print(f"SUCCESS: Order correctly identified as Rejected/Failed.")
            elif data and 'orderId' in data and data['orderId'] == '1001':
                    print(f"SUCCESS: Response contains Order ID (handled).")
            else:
                    print(f"Response content: {data}")

            print("-" * 30)

    finally:
        for p in active_patches:
            try:
                p.stop()
            except:
                pass

    print("\nDiagnostic Complete.")

if __name__ == "__main__":
    run_diagnostic()
