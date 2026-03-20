"""
Token store mapping MCP access tokens to Google OAuth credentials.
Uses a JSON file on disk (/tmp/mcp-tokens.json) for persistence within a Cloud Run instance.
"""

import json
import logging
import os
import threading
from pathlib import Path

from google.oauth2.credentials import Credentials

from ..config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

logger = logging.getLogger(__name__)

TOKEN_STORE_PATH = Path(os.environ.get("MCP_TOKEN_STORE", "/tmp/mcp-tokens.json"))

# Google OAuth scopes we request
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


class TokenStore:
    """Maps MCP access tokens to Google OAuth refresh tokens."""

    def __init__(self):
        self._lock = threading.Lock()
        # In-memory cache: mcp_access_token -> google_token_data
        self._tokens: dict[str, dict] = {}
        self._load()

    def _load(self):
        if TOKEN_STORE_PATH.exists():
            try:
                with open(TOKEN_STORE_PATH) as f:
                    self._tokens = json.load(f)
                logger.info(f"Loaded {len(self._tokens)} token mappings from {TOKEN_STORE_PATH}")
            except Exception as e:
                logger.warning(f"Failed to load token store: {e}")
                self._tokens = {}

    def _save(self):
        try:
            TOKEN_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_STORE_PATH, "w") as f:
                json.dump(self._tokens, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save token store: {e}")

    def store_google_token(self, mcp_auth_code: str, google_token_data: dict):
        """Store Google token data mapped to an MCP auth code (pre-exchange).
        Will be re-mapped when the MCP auth code is exchanged for an access token."""
        with self._lock:
            # Store under auth_code prefix temporarily
            self._tokens[f"authcode:{mcp_auth_code}"] = google_token_data
            self._save()
        logger.info(f"Stored Google token for MCP auth code {mcp_auth_code[:8]}...")

    def promote_auth_code_to_access_token(self, mcp_auth_code: str, mcp_access_token: str):
        """When MCP exchanges auth code for access token, re-map the Google token."""
        with self._lock:
            key = f"authcode:{mcp_auth_code}"
            google_data = self._tokens.pop(key, None)
            if google_data:
                self._tokens[mcp_access_token] = google_data
                self._save()
                logger.info(f"Promoted auth code to access token mapping")
            else:
                logger.warning(f"No Google token found for auth code {mcp_auth_code[:8]}...")

    def promote_access_token(self, old_token: str, new_token: str):
        """When MCP refreshes, move the Google token to the new access token."""
        with self._lock:
            google_data = self._tokens.pop(old_token, None)
            if google_data:
                self._tokens[new_token] = google_data
                self._save()

    def get_google_credentials(self, mcp_access_token: str) -> Credentials | None:
        """Get Google credentials for a given MCP access token."""
        with self._lock:
            google_data = self._tokens.get(mcp_access_token)
        if not google_data:
            return None
        return Credentials(
            token=google_data.get("access_token"),
            refresh_token=google_data["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=GOOGLE_SCOPES,
        )


# Singleton
token_store = TokenStore()
