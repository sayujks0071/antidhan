import secrets
from typing import List, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from packages.core.config import settings


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce API key authentication on all endpoints
    except public ones (health, metrics, docs).
    """

    def __init__(self, app, public_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.public_paths = public_paths or [
            "/",
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc"
        ]

    async def dispatch(self, request: Request, call_next):
        # Allow OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check if path is public (handling trailing slashes)
        path = request.url.path.rstrip("/")
        if not path:
             path = "/"

        for public_path in self.public_paths:
            normalized_public_path = public_path.rstrip("/")
            if not normalized_public_path:
                normalized_public_path = "/"

            if path == normalized_public_path or path.startswith(normalized_public_path + "/"):
                return await call_next(request)

        # Get API key from header
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing X-API-Key header"}
            )

        # Validate API key (constant time comparison)
        if not secrets.compare_digest(api_key, settings.api_secret_key):
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid API key"}
            )

        return await call_next(request)
