"""
Helper to get Google credentials for the current request from the MCP auth context.
"""

import logging
from google.oauth2.credentials import Credentials

from mcp.server.auth.middleware.auth_context import get_access_token

from .token_store import token_store
from .credentials import get_google_credentials as get_fallback_credentials

logger = logging.getLogger(__name__)


def get_current_google_credentials() -> Credentials:
    """
    Get Google credentials for the current authenticated MCP user.
    Falls back to env-based credentials if no per-user token is found
    (backward compatibility for stdio/local usage).
    """
    access_token = get_access_token()
    if access_token:
        creds = token_store.get_google_credentials(access_token.token)
        if creds:
            logger.debug("Using per-user Google credentials")
            return creds
        logger.warning(
            f"No Google token found for MCP token {access_token.token[:8]}..., "
            "falling back to env credentials"
        )

    # Fallback: env vars / local credentials file (for stdio transport)
    return get_fallback_credentials()
