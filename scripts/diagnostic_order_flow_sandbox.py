
import os
import sys
import json
from unittest.mock import MagicMock, patch

# Set environment variables for testing
os.environ["API_KEY_PEPPER"] = "test_pepper"
os.environ["APP_KEY"] = "test_app_key"
os.environ["BROKER_API_KEY"] = "test_client_id"
os.environ["BROKER_API_SECRET"] = "test_access_token"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["FLASK_ENV"] = "testing"
os.environ["CSRF_ENABLED"] = "FALSE" # Disable CSRF for testing

# Add openalgo to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../openalgo')))

# Mock openalgo_observability
mock_observability = MagicMock()
sys.modules["openalgo_observability"] = mock_observability
sys.modules["openalgo_observability.logging_setup"] = mock_observability

# Mock utils.env_check
mock_env_check = MagicMock()
sys.modules["utils.env_check"] = mock_env_check

# Mock websocket proxy and ngrok manager to prevent startup hangs
sys.modules["websocket_proxy"] = MagicMock()
sys.modules["websocket_proxy.app_integration"] = MagicMock()
sys.modules["utils.ngrok_manager"] = MagicMock()

# Mock security middleware to prevent IP blocking
sys.modules["utils.security_middleware"] = MagicMock()

# Mock database modules to avoid import errors and side effects during app import
# We need to mock every module that app.py imports from database/
db_modules = [
    "database",
    "database.settings_db",
    "database.auth_db",
    "database.user_db",
    "database.symbol",
    "database.apilog_db",
    "database.analyzer_db",
    "database.chartink_db",
    "database.traffic_db",
    "database.latency_db",
    "database.strategy_db",
    "database.sandbox_db",
    "database.action_center_db",
    "database.chart_prefs_db",
    "database.market_calendar_db",
    "database.qty_freeze_db",
    "database.historify_db",
    "database.flow_db",
    "database.token_db",
    "database.master_contract_status_db",
    "database.telegram_db",
    "database.token_db_enhanced",
    "database.cache_restoration",
    "database.master_contract_cache_hook",
    "database.cache_invalidation"
]

for mod in db_modules:
    m = MagicMock()
    # Ensure init_db exists on the mock
    m.init_db = MagicMock()
    # Ensure other functions exist
    m.ensure_chart_prefs_tables_exists = MagicMock()
    m.ensure_market_calendar_tables_exists = MagicMock()
    m.ensure_qty_freeze_tables_exists = MagicMock()
    m.init_database = MagicMock()
    m.init_latency_db = MagicMock()
    m.init_logs_db = MagicMock()
    m.get_bot_config = MagicMock(return_value={})
    m.restore_all_caches = MagicMock(return_value={"success": True, "symbol_cache": {}, "auth_cache": {}})
    # For token_db
    m.get_token = MagicMock(return_value="12345")
    # For settings_db
    m.get_analyze_mode = MagicMock(return_value=False) # Disable analyze mode during startup to avoid thread creation
    m.get_config = MagicMock(return_value="10000000.00") # Return string for Decimal conversion

    sys.modules[mod] = m

# Mock sandbox threads to prevent them from starting
sys.modules["sandbox.execution_thread"] = MagicMock()
sys.modules["sandbox.squareoff_thread"] = MagicMock()

# Mock Sandbox Managers with proper return values
mock_pm_class = MagicMock()
mock_pm_instance = MagicMock()
mock_pm_class.return_value = mock_pm_instance
mock_pm_instance.get_open_positions.return_value = (True, {"data": []}, 200)

mock_om_class = MagicMock()
mock_om_instance = MagicMock()
mock_om_class.return_value = mock_om_instance
mock_om_instance.place_order.return_value = (True, {"status": "success", "orderid": "1001", "message": "Order Placed"}, 200)

mock_fm_class = MagicMock()
mock_fm_instance = MagicMock()
mock_fm_class.return_value = mock_fm_instance

mock_hm_class = MagicMock()
mock_hm_instance = MagicMock()
mock_hm_class.return_value = mock_hm_instance

mock_pm_module = MagicMock()
mock_pm_module.PositionManager = mock_pm_class
sys.modules["sandbox.position_manager"] = mock_pm_module

mock_om_module = MagicMock()
mock_om_module.OrderManager = mock_om_class
sys.modules["sandbox.order_manager"] = mock_om_module

mock_fm_module = MagicMock()
mock_fm_module.FundManager = mock_fm_class
sys.modules["sandbox.fund_manager"] = mock_fm_module

mock_hm_module = MagicMock()
mock_hm_module.HoldingsManager = mock_hm_class
sys.modules["sandbox.holdings_manager"] = mock_hm_module

# Now import app
try:
    from app import app
except ImportError as e:
    print(f"Failed to import app: {e}")
    sys.exit(1)

def run_diagnostics():
    print("Starting Order Flow Diagnostics...")
    client = app.test_client()

    order_types = [
        {"type": "LIMIT", "params": {"pricetype": "LIMIT", "price": "100"}},
        {"type": "MARKET", "params": {"pricetype": "MARKET", "price": "0"}},
        {"type": "SL", "params": {"pricetype": "SL", "price": "100", "trigger_price": "90"}},
        {"type": "SL-M", "params": {"pricetype": "SL-M", "price": "0", "trigger_price": "90"}},
        {"type": "BO", "params": {"pricetype": "LIMIT", "price": "100", "product": "BO", "stop_loss": "10", "square_off": "10"}},
    ]

    # Patch functions in blueprints/services that depend on DB or external calls
    with patch('blueprints.orders.get_auth_token', return_value="test_token"), \
         patch('blueprints.orders.get_api_key_for_tradingview', return_value="test_api_key"), \
         patch('blueprints.orders.get_analyze_mode', return_value=True), \
         patch('services.place_smart_order_service.get_analyze_mode', return_value=True), \
         patch('services.sandbox_service.get_analyze_mode', return_value=True), \
         patch('blueprints.orders.get_token', return_value="12345"), \
         patch('services.place_smart_order_service.get_token', return_value="12345"), \
         patch('broker.dhan_sandbox.api.order_api.get_token', return_value="12345"), \
         patch('broker.dhan_sandbox.api.order_api.get_open_position', return_value="0"), \
         patch('utils.session.is_session_valid', return_value=True), \
         patch('database.auth_db.verify_api_key', return_value="test_user_id"), \
         patch('broker.dhan_sandbox.api.order_api.place_order_api') as mock_place_order:

        # Setup mock response for place_order_api
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Simulate a successful API call that returns a REJECTED status (common in sandbox/after hours)
        mock_data = {
            "status": "success",
            "data": {
                "orderStatus": "REJECTED",
                "rejectReason": "Market is closed",
                "orderId": "1001"
            },
            "orderId": "1001",
            "message": "Order placed"
        }
        mock_place_order.return_value = (mock_response, mock_data, "1001")

        # Setup Session
        with client.session_transaction() as sess:
            sess['user'] = 'test_user'
            sess['broker'] = 'dhan_sandbox'
            sess['logged_in'] = True

        for order_info in order_types:
            print(f"\nTesting {order_info['type']} Order...")

            payload = {
                "apikey": "test_api_key",
                "strategy": "Diagnostic Test",
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "BUY",
                "product": "MIS",
                "quantity": "1",
                "position_size": "1",
                "price": "0",
                "trigger_price": "0",
                "disclosed_quantity": "0",
            }
            payload.update(order_info['params'])

            response = client.post('/placesmartorder',
                                 data=json.dumps(payload),
                                 content_type='application/json')

            print(f"HTTP Status: {response.status_code}")
            try:
                data = response.get_json()
                print(f"Response Data: {data}")

                # Validation logic
                if response.status_code == 200:
                    # Blueprint should return success even if broker rejected order (it returns the broker response)
                    # Or it might return error if it checks status.
                    # orders.py: return jsonify(response_data), status_code
                    # place_smart_order_service returns success=True if API call worked (even if order rejected logic varies)

                    if data.get("status") == "success" or "orderId" in data or "orderid" in data:
                        print("✅ Handled correctly")
                    elif data.get("status") == "error":
                         print(f"⚠️ Handled as error: {data.get('message')}")
                    else:
                        print(f"⚠️ Unexpected JSON content: {data}")
                else:
                     print(f"❌ Failed: HTTP {response.status_code}")

            except Exception as e:
                print(f"❌ Failed to parse JSON: {e}")
                print(response.data)

if __name__ == "__main__":
    run_diagnostics()
