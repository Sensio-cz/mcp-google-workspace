"""
Helper to get Google credentials for the current request from the MCP auth context.
"""

import logging
import os

from google.oauth2.credentials import Credentials

from mcp.server.auth.middleware.auth_context import get_access_token

from .token_store import token_store, google_credentials_z_tokenu, email_z_tokenu
from .credentials import get_google_credentials as get_fallback_credentials

logger = logging.getLogger(__name__)


def current_user_key() -> str:
    """Kdo je prihlaseny - klic pro cache s daty konkretniho uzivatele.

    Instance sluzeb je jedna pro cely server, takze cokoli cachovaneho bez
    tohoto klice se ukaze i ostatnim uzivatelum. Lokalni stdio beh nema MCP
    token a je jednouzivatelsky, proto "local".
    """
    access_token = get_access_token()
    if access_token:
        return email_z_tokenu(access_token.token)
    return "local"


def get_current_google_credentials() -> Credentials:
    """
    Get Google credentials for the current authenticated MCP user.
    Falls back to env-based credentials if no per-user token is found
    (backward compatibility for stdio/local usage).
    """
    access_token = get_access_token()
    if access_token:
        creds = google_credentials_z_tokenu(access_token.token)
        if creds:
            user_email = email_z_tokenu(access_token.token)
            logger.info(f"[TOOL] Uživatel: {user_email}")
            token_store.track_tool_call(user_email)
            return creds
        logger.warning(
            "MCP token nenese Google udaje. Nejspis jde o token vydany starsi "
            "verzi serveru - staci konektor znovu pripojit."
        )

    # V HTTP REZIMU SE NA ENV CREDENTIALS NEPADA. Ty patri majiteli serveru,
    # takze by prihlaseny cizi uzivatel dostal do ruky JEHO schranku. Puvodni
    # pojistka v credentials.py se testuje az po nacteni promenne, takze
    # nechrani - zmereno nezavislym reviewem 22. 9. 2026.
    if os.environ.get("MCP_TRANSPORT", "stdio") != "stdio":
        raise PermissionError(
            "Tenhle MCP token nenese Google pristup. Odpoj a znovu pripoj konektor."
        )

    # Fallback: env vars / local credentials file (for stdio transport)
    return get_fallback_credentials()
