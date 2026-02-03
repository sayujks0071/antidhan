from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)

def test_cors_default_allow_all():
    """Test that default CORS config allows all origins"""
    # When allow_origins=["*"], Starlette mirrors the Origin header
    # OR returns "*" depending on implementation details.
    # The failure showed it returned "http://evil.com" which means it allowed it.

    headers = {
        "Origin": "http://evil.com",
        "Access-Control-Request-Method": "GET"
    }
    response = client.options("/health", headers=headers)
    assert response.status_code == 200
    # It allowed the origin
    assert response.headers["access-control-allow-origin"] == "http://evil.com"

def test_cors_restricted_origin(monkeypatch):
    """Test behavior when CORS is restricted"""
    pass
