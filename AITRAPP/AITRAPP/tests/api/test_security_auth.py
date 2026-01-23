import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from packages.core.config import settings

client = TestClient(app)

def test_health_check_public_access():
    """Test that health check endpoint is publicly accessible without API key"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_metrics_public_access():
    """Test that metrics endpoint is publicly accessible without API key"""
    response = client.get("/metrics")
    assert response.status_code == 200

def test_root_public_access():
    """Test that root endpoint is publicly accessible without API key"""
    response = client.get("/")
    assert response.status_code == 200

def test_docs_public_access_with_trailing_slash():
    """Test that docs endpoint is accessible with trailing slash"""
    # Note: /docs is usually a redirect to /docs/ or handled by Swagger UI
    # We just check we don't get 401/403
    response = client.get("/docs/")
    assert response.status_code not in [401, 403]

    response = client.get("/docs")
    assert response.status_code not in [401, 403]

def test_protected_endpoint_missing_key():
    """Test that protected endpoint fails without API key"""
    # /positions is a protected endpoint
    response = client.get("/positions")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing X-API-Key header"

def test_protected_endpoint_invalid_key():
    """Test that protected endpoint fails with invalid API key"""
    headers = {"X-API-Key": "invalid_key"}
    response = client.get("/positions", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API key"

def test_protected_endpoint_valid_key(mocker):
    """Test that protected endpoint succeeds with valid API key"""

    # Mock Orchestrator to avoid logic errors during state access
    # We only care about Auth passing here, not the actual endpoint logic success

    headers = {"X-API-Key": settings.api_secret_key}

    # We expect this might fail with 500 or return empty list because app_state is not fully initialized in test
    # But as long as it is not 401 or 403, Auth worked.

    response = client.get("/positions", headers=headers)

    assert response.status_code not in [401, 403]
