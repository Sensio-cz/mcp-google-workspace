"""
In-memory OAuth provider for PoC testing with claude.ai custom connectors.
Implements OAuthAuthorizationServerProvider protocol from MCP SDK.
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

logger = logging.getLogger(__name__)

# Token validity
ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 86400 * 30  # 30 days
AUTH_CODE_TTL = 300  # 5 minutes


class InMemoryOAuthProvider:
    """
    Minimal in-memory OAuth provider for PoC.
    Accepts any client via dynamic registration.
    Issues tokens mapped to a test user.
    """

    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")
        # In-memory stores
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}
        # Map auth code -> pending params (for the consent page flow)
        self._pending_authorizations: dict[str, dict] = {}

    # --- Client Registration ---

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            client_info.client_id = f"client_{secrets.token_hex(16)}"
        client_info.client_id_issued_at = int(time.time())
        self._clients[client_info.client_id] = client_info
        logger.info(f"Registered client: {client_info.client_id}")

    # --- Authorization ---

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """
        Returns URL to a consent page. For this PoC we auto-approve and redirect
        back with an auth code immediately (no HTML form needed since we want
        minimal friction for testing).
        """
        # Generate authorization code
        code = secrets.token_urlsafe(32)
        now = time.time()

        auth_code = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=now + AUTH_CODE_TTL,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        self._auth_codes[code] = auth_code
        logger.info(f"Issued auth code for client {client.client_id}")

        # Build redirect back to the client with the code
        redirect_url = construct_redirect_uri(
            str(params.redirect_uri),
            code=code,
            state=params.state,
        )
        return redirect_url

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

        # New access token
        access_token_str = secrets.token_urlsafe(32)
        access_token = AccessToken(
            token=access_token_str,
            client_id=client.client_id,
            scopes=use_scopes,
            expires_at=now + ACCESS_TOKEN_TTL,
        )
        self._access_tokens[access_token_str] = access_token

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
