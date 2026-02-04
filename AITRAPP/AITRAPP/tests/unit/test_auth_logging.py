import logging

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)

def test_callback_logs_mask_request_token(caplog):
    """Verify that request_token is masked in error logs when status is failure"""
    caplog.set_level(logging.ERROR)

    request_token = "secret_request_token_123"

    # Trigger the callback with failure status
    # This hits the block: if status != "success": logger.error(...)
    response = client.get(f"/auth/kite/callback?request_token={request_token}&status=failure")

    assert response.status_code == 400

    # Check logs
    log_text = caplog.text
    assert "Kite login failed" in log_text
    assert "***" in log_text
    # The crucial check: the actual token should NOT be in the logs
    assert request_token not in log_text

def test_callback_logs_mask_params_obj(caplog):
    """Verify that even if params are printed, sensitive keys are masked"""
    caplog.set_level(logging.ERROR)
    request_token = "another_secret_token"

    response = client.get(f"/auth/kite/callback?request_token={request_token}&status=failure&other=value")

    assert response.status_code == 400
    log_text = caplog.text

    assert "'request_token': '***'" in log_text or "'request_token': '***'" in log_text.replace('"', "'")
    assert request_token not in log_text
