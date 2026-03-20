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
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


class TokenStore:
    """Maps MCP access tokens to Google OAuth refresh tokens."""

    def __init__(self):
        self._lock = threading.Lock()
        # In-memory cache: mcp_access_token -> google_token_data
        self._tokens: dict[str, dict] = {}
        # Usage stats: email -> {tool_calls, first_seen, last_seen, errors}
        self._stats: dict[str, dict] = {}
        self._stats_path = TOKEN_STORE_PATH.parent / "mcp-stats.json"
        self._load()
        self._load_stats()

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

    def _load_stats(self):
        if self._stats_path.exists():
            try:
                with open(self._stats_path) as f:
                    self._stats = json.load(f)
            except Exception:
                self._stats = {}

    def _save_stats(self):
        try:
            self._stats_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._stats_path, "w") as f:
                json.dump(self._stats, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")

    def track_tool_call(self, email: str, tool_name: str = "", error: bool = False):
        """Zaznamenej tool call pro statistiky."""
        from datetime import datetime
        now = datetime.now().strftime("%d. %m. %Y, %H:%M")
        with self._lock:
            if email not in self._stats:
                self._stats[email] = {
                    "tool_calls": 0,
                    "errors": 0,
                    "first_seen": now,
                    "last_seen": now,
                    "tools_used": {},
                }
            self._stats[email]["tool_calls"] += 1
            self._stats[email]["last_seen"] = now
            if error:
                self._stats[email]["errors"] += 1
            if tool_name:
                tools = self._stats[email]["tools_used"]
                tools[tool_name] = tools.get(tool_name, 0) + 1
            self._save_stats()

    def track_login(self, email: str):
        """Zaznamenej přihlášení uživatele."""
        from datetime import datetime
        now = datetime.now().strftime("%d. %m. %Y, %H:%M")
        with self._lock:
            if email not in self._stats:
                self._stats[email] = {
                    "tool_calls": 0,
                    "errors": 0,
                    "first_seen": now,
                    "last_seen": now,
                    "tools_used": {},
                }
            self._stats[email]["last_login"] = now
            self._save_stats()

    def get_usage_stats(self) -> dict:
        """Vrať statistiky pro status stránku."""
        with self._lock:
            total_users = len(self._stats)
            total_calls = sum(s.get("tool_calls", 0) for s in self._stats.values())
            total_errors = sum(s.get("errors", 0) for s in self._stats.values())
            users = []
            for email, s in self._stats.items():
                users.append({
                    "email": email,
                    "tool_calls": s.get("tool_calls", 0),
                    "errors": s.get("errors", 0),
                    "first_seen": s.get("first_seen", "?"),
                    "last_seen": s.get("last_seen", "?"),
                    "last_login": s.get("last_login", "?"),
                })
            return {
                "total_users": total_users,
                "total_tool_calls": total_calls,
                "total_errors": total_errors,
                "users": users,
            }

    def get_user_email(self, mcp_access_token: str) -> str:
        """Get user email for a given MCP access token."""
        with self._lock:
            google_data = self._tokens.get(mcp_access_token)
        if not google_data:
            return "unknown"
        return google_data.get("user_email", "unknown")

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
