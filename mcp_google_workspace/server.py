import os
import logging
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.auth.provider import construct_redirect_uri
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse

from .auth.oauth_provider import GoogleProxyOAuthProvider
from .auth.token_store import token_store
from .config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

logger = logging.getLogger(__name__)

SERVER_URL = os.environ.get(
    "MCP_SERVER_URL",
    "https://mcp-google-workspace-581084999054.europe-west1.run.app",
)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

oauth_provider = GoogleProxyOAuthProvider(
    server_url=SERVER_URL,
    google_client_id=GOOGLE_CLIENT_ID,
    google_client_secret=GOOGLE_CLIENT_SECRET,
)

mcp = FastMCP(
    name="mcp-google-workspace",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8080")),
    auth_server_provider=oauth_provider,
    auth=AuthSettings(
        issuer_url=SERVER_URL,
        resource_server_url=SERVER_URL,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["mcp:tools"],
            default_scopes=["mcp:tools"],
        ),
        revocation_options=RevocationOptions(enabled=True),
    ),
)


@mcp.custom_route("/", methods=["GET"])
async def status_page(request: Request):
    """Status stránka MCP serveru."""
    from importlib.metadata import version as pkg_version
    try:
        ver = pkg_version("mcp-google-workspace")
    except Exception:
        ver = "dev"

    tools_count = len(mcp._tool_manager._tools) if hasattr(mcp, '_tool_manager') else "?"

    html = f"""<html>
<head>
<meta charset="utf-8">
<title>Sensio MCP Google Workspace</title>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Barlow', Arial, sans-serif; background: #f5f7fa; display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
  .card {{ background: white; border-radius: 12px; padding: 48px; max-width: 500px; text-align: center; box-shadow: 0 4px 24px rgba(28,62,99,0.1); }}
  .logo {{ color: #1C3E63; font-size: 28px; font-weight: 700; margin-bottom: 24px; }}
  .logo span {{ color: #D67E29; }}
  .status {{ display: inline-block; background: #C5DB33; color: white; padding: 4px 16px; border-radius: 20px; font-weight: 600; font-size: 14px; margin-bottom: 24px; }}
  h1 {{ color: #1C3E63; font-size: 20px; font-weight: 600; margin-bottom: 16px; }}
  .info {{ color: #555; font-size: 14px; line-height: 1.8; text-align: left; }}
  .info strong {{ color: #1C3E63; }}
  .footer {{ margin-top: 24px; color: #999; font-size: 12px; }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">sensio<span>.cz</span></div>
  <div class="status">Online</div>
  <h1>MCP Google Workspace</h1>
  <div class="info">
    <strong>Verze:</strong> {ver}<br>
    <strong>Dostupne tools:</strong> {tools_count}<br>
    <strong>Sluzby:</strong> Gmail, Google Drive, Google Sheets<br>
    <strong>Autentizace:</strong> OAuth 2.0 (Google)<br>
    <strong>MCP endpoint:</strong> <code>/mcp</code>
  </div>
  <div class="footer">Sensio.cz s.r.o. - MCP server pro AI asistenty</div>
</div>
</body>
</html>"""
    from starlette.responses import HTMLResponse
    return HTMLResponse(html)


@mcp.custom_route("/google/callback", methods=["GET"])
async def google_callback(request: Request):
    """
    Google OAuth callback. Receives the Google auth code, exchanges it for tokens,
    stores the Google token, then completes the MCP OAuth flow by redirecting
    back to claude.ai with the MCP auth code.
    """
    error = request.query_params.get("error")
    if error:
        logger.error(f"Google OAuth error: {error}")
        return JSONResponse({"error": f"Google OAuth error: {error}"}, status_code=400)

    google_code = request.query_params.get("code")
    google_state = request.query_params.get("state")

    if not google_code or not google_state:
        return JSONResponse({"error": "Missing code or state from Google"}, status_code=400)

    # Look up the pending MCP authorization
    pending = oauth_provider.get_pending_auth(google_state)
    if not pending:
        return JSONResponse({"error": "Invalid or expired state"}, status_code=400)

    client_id = pending["client_id"]
    mcp_params = pending["params"]

    # Exchange Google auth code for Google tokens
    google_redirect_uri = f"{SERVER_URL}/google/callback"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": google_code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            google_tokens = resp.json()
    except Exception as e:
        logger.error(f"Failed to exchange Google auth code: {e}")
        return JSONResponse({"error": "Failed to exchange Google auth code"}, status_code=500)

    if "refresh_token" not in google_tokens:
        logger.error("Google did not return a refresh_token. User may need to revoke and re-authorize.")
        return JSONResponse(
            {"error": "No refresh_token from Google. Try revoking access at https://myaccount.google.com/permissions and retry."},
            status_code=400,
        )

    # Create MCP auth code
    mcp_code = oauth_provider.create_auth_code_for_client(client_id, mcp_params)

    # Store Google token mapped to MCP auth code (will be promoted on exchange)
    token_store.store_google_token(mcp_code, {
        "access_token": google_tokens.get("access_token"),
        "refresh_token": google_tokens["refresh_token"],
        "token_type": google_tokens.get("token_type", "Bearer"),
        "expires_in": google_tokens.get("expires_in"),
    })

    # Redirect back to claude.ai with the MCP auth code
    redirect_url = construct_redirect_uri(
        str(mcp_params.redirect_uri),
        code=mcp_code,
        state=mcp_params.state,
    )

    logger.info(f"Google OAuth complete for client {client_id}, redirecting to claude.ai")
    return RedirectResponse(url=redirect_url, status_code=302)
