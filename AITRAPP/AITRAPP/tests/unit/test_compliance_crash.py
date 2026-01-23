
import pytest
from unittest.mock import patch

def test_compliance_module_imports():
    """Test that packages.core.compliance can be imported without NameError"""
    try:
        from packages.core import compliance

        # Verify critical objects exist and are not None
        assert compliance.ComplianceManager is not None
        assert compliance.check_static_ip is not None
        assert compliance.check_oauth_fresh is not None
        assert compliance.check_family_only is not None
        assert compliance.tops_cap_ok is not None
        assert compliance.algo_id_present is not None

    except ImportError as e:
        pytest.fail(f"Failed to import compliance module: {e}")
    except AttributeError as e:
        pytest.fail(f"Missing attribute in compliance module: {e}")

@pytest.mark.asyncio
async def test_compliance_manager_init():
    """Test that ComplianceManager can be instantiated"""
    from packages.core.compliance import ComplianceManager

    cm = ComplianceManager()
    assert cm.static_ip_verified is False
    assert cm.oauth_fresh is False
    assert cm.order_count_window == []
    # tops_cap should be integer (default or env)
    assert isinstance(cm.tops_cap, int)

@pytest.mark.asyncio
async def test_api_main_compliance_integration():
    """Test that apps.api.main imports compliance correctly"""
    # We need to mock a lot of things to import main because it initializes global state
    with patch('packages.core.metrics.get_metrics'), \
         patch('packages.core.redis_bus.RedisBus'), \
         patch('kiteconnect.KiteConnect'):

        try:
            from apps.api import main
            assert main.compliance is not None
        except ImportError as e:
            pytest.fail(f"Failed to import apps.api.main: {e}")
        except AttributeError as e:
            pytest.fail(f"apps.api.main missing compliance attribute: {e}")
