"""
OAuth provider that proxies Google OAuth for multi-user authentication.
When claude.ai calls /authorize, the user is redirected to Google OAuth.
After Google login, the Google token is stored and mapped to the MCP token.
"""

import secrets
import time
import logging
from urllib.parse import urlencode

from pydantic import AnyUrl
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AccessToken,
    RefreshToken,
    OAuthAuthorizationServerProvider,
    construct_redirect_uri,
)

from .token_store import token_store, GOOGLE_SCOPES

logger = logging.getLogger(__name__)

# Token validity
ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 86400 * 30  # 30 days
AUTH_CODE_TTL = 300  # 5 minutes

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class GoogleProxyOAuthProvider:
    """
    OAuth provider that redirects to Google OAuth during authorization.
    Maps MCP tokens to per-user Google tokens.
    """

    def __init__(self, server_url: str, google_client_id: str, google_client_secret: str):
        self.server_url = server_url.rstrip("/")
        self.google_client_id = google_client_id
        self.google_client_secret = google_client_secret
        # In-memory stores
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}
        # Pending Google OAuth states: google_state -> {client, params}
        self._pending_google_auth: dict[str, dict] = {}

    # --- Client Registration ---

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            client_info.client_id = f"client_{secrets.token_hex(16)}"
        client_info.client_id_issued_at = int(time.time())
        self._clients[client_info.client_id] = client_info
        logger.info(f"Registered client: {client_info.client_id}")

    # --- Authorization (redirects to Google) ---

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """
        Instead of auto-approving, redirect user to Google OAuth.
        After Google login, /google/callback completes the MCP flow.
        """
        # Generate a state token to link Google callback back to this MCP auth request
        google_state = secrets.token_urlsafe(32)

        # Store the pending MCP authorization params
        self._pending_google_auth[google_state] = {
            "client_id": client.client_id,
            "params": params,
            "created_at": time.time(),
        }

        # Build Google OAuth URL
        google_redirect_uri = f"{self.server_url}/google/callback"
        google_params = {
            "client_id": self.google_client_id,
            "redirect_uri": google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": google_state,
        }

        google_url = f"{GOOGLE_AUTH_URL}?{urlencode(google_params)}"
        logger.info(f"Redirecting to Google OAuth for client {client.client_id}")
        return google_url

    def get_pending_auth(self, google_state: str) -> dict | None:
        """Retrieve and remove a pending Google auth by state."""
        pending = self._pending_google_auth.pop(google_state, None)
        if pending and time.time() - pending["created_at"] > AUTH_CODE_TTL:
            logger.warning("Pending Google auth expired")
            return None
        return pending

    def create_auth_code_for_client(
        self, client_id: str, params: AuthorizationParams
    ) -> str:
        """Create an MCP auth code after Google OAuth succeeds. Returns the code string."""
        code = secrets.token_urlsafe(32)
        now = time.time()

        auth_code = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=now + AUTH_CODE_TTL,
            client_id=client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        self._auth_codes[code] = auth_code
        logger.info(f"Issued MCP auth code for client {client_id} after Google OAuth")
        return code

    # --- Authorization Code ---

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code_obj = self._auth_codes.get(authorization_code)
        if code_obj is None:
            return None
        if code_obj.client_id != client.client_id:
            return None
        if time.time() > code_obj.expires_at:
            del self._auth_codes[authorization_code]
            return None
        return code_obj

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # Remove used code
        self._auth_codes.pop(authorization_code.code, None)

        now = int(time.time())

        # Generate access token
        access_token_str = secrets.token_urlsafe(32)
        access_token = AccessToken(
            token=access_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=now + ACCESS_TOKEN_TTL,
            resource=authorization_code.resource,
        )
        self._access_tokens[access_token_str] = access_token

        # Generate refresh token
        refresh_token_str = secrets.token_urlsafe(32)
        refresh_token = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=now + REFRESH_TOKEN_TTL,
        )
        self._refresh_tokens[refresh_token_str] = refresh_token

        # Promote the Google token mapping from auth code to access token
        token_store.promote_auth_code_to_access_token(authorization_code.code, access_token_str)

        logger.info(f"Exchanged auth code for tokens, client={client.client_id}")

        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=refresh_token_str,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    # --- Refresh Token ---

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        token_obj = self._refresh_tokens.get(refresh_token)
        if token_obj is None:
            return None
        if token_obj.client_id != client.client_id:
            return None
        if token_obj.expires_at and time.time() > token_obj.expires_at:
            del self._refresh_tokens[refresh_token]
            return None
        return token_obj

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Revoke old refresh token
        self._refresh_tokens.pop(refresh_token.token, None)

        now = int(time.time())
        use_scopes = scopes or refresh_token.scopes

        # Find old access token to migrate Google token mapping
        old_access_token = None
        for token_str, at in self._access_tokens.items():
            if at.client_id == client.client_id:
                old_access_token = token_str
                break

        # New access token
        access_token_str = secrets.token_urlsafe(32)
        access_token = AccessToken(
            token=access_token_str,
            client_id=client.client_id,
            scopes=use_scopes,
            expires_at=now + ACCESS_TOKEN_TTL,
        )
        self._access_tokens[access_token_str] = access_token

        # Migrate Google token mapping
        if old_access_token:
            self._access_tokens.pop(old_access_token, None)
            token_store.promote_access_token(old_access_token, access_token_str)

        # New refresh token
        new_refresh_str = secrets.token_urlsafe(32)
        new_refresh = RefreshToken(
            token=new_refresh_str,
            client_id=client.client_id,
            scopes=use_scopes,
            expires_at=now + REFRESH_TOKEN_TTL,
        )
        self._refresh_tokens[new_refresh_str] = new_refresh

        logger.info(f"Refreshed tokens for client={client.client_id}")

        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=new_refresh_str,
            scope=" ".join(use_scopes) if use_scopes else None,
        )

    # --- Access Token Verification ---

    async def load_access_token(self, token: str) -> AccessToken | None:
        access_token = self._access_tokens.get(token)
        if access_token is None:
            return None
        if access_token.expires_at and time.time() > access_token.expires_at:
            del self._access_tokens[token]
            return None
        return access_token

    # --- Revocation ---

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
        elif isinstance(token, RefreshToken):
            self._refresh_tokens.pop(token.token, None)
        logger.info(f"Revoked token for client={token.client_id}")
