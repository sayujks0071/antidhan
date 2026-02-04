import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.auth.kite_auth import KiteAuth

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/auth/kite/callback", response_class=HTMLResponse)
async def kite_callback(request: Request):
    """
    Callback endpoint for Kite Connect login.
    Receives request_token, exchanges it for access_token, and stores it.
    """
    params = request.query_params
    request_token = params.get("request_token")
    status = params.get("status")

    if status != "success":
        # Mask request_token in logs
        safe_params = dict(params)
        if "request_token" in safe_params:
            safe_params["request_token"] = "***"
        logger.error(f"Kite login failed: {safe_params}")
        return HTMLResponse(content="<h1>Auth Failed</h1><p>Status was not success.</p>", status_code=400)

    if not request_token:
        logger.error("No request_token provided in callback")
        return HTMLResponse(content="<h1>Auth Failed</h1><p>Missing request_token.</p>", status_code=400)

    logger.info("Callback received with request_token.")

    try:
        auth = KiteAuth()
        access_token = auth.exchange_request_token(request_token)
        auth.persist_access_token(access_token)

        logger.info("Token exchanged and persisted successfully via callback.")

        return HTMLResponse(content="""
        <html>
            <head><title>Auth Success</title></head>
            <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
                <h1 style="color: green;">Authentication Successful</h1>
                <p>The access token has been securely stored.</p>
                <p>You may close this window and restart your application/services if necessary.</p>
            </body>
        </html>
        """)
    except Exception as e:
        logger.error(f"Error in kite callback: {e}")
        # SECURITY: Do not leak exception details to the user
        return HTMLResponse(content="<h1>Auth Error</h1><p>Authentication failed. Please check application logs for details.</p>", status_code=500)
