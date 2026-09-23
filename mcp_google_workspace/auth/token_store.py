"""
Statistiky pouziti a stavba Google credentials z obsahu MCP tokenu.

UZ TO NENI ULOZISTE PRISTUPU. Puvodne tenhle soubor mapoval MCP tokeny na
Google tokeny a drzel je v `/tmp/mcp-tokens.json`, tedy na disku JEDNE instance
Cloud Runu - jak rikala i jeho puvodni hlavicka ("within a Cloud Run instance").
Jakmile Cloud Run instanci uspal nebo pridal druhou, pristup se ztratil
a kazde volani skoncilo `invalid_token`. Google refresh token proto dnes
putuje zapecceny primo v MCP tokenu (auth/sealed.py) a tady zustavaji jen
statistiky.

STATISTIKY ZUSTAVAJI V /tmp A JE TO VEDOME: jsou to cisla do status stranky,
ne pristup. Kdyz se instance uspi, cast historie se ztrati - to nikomu
nezabrani v praci. Trvale by potrebovaly sdilene uloziste (Firestore),
coz je samostatne rozhodnuti.
"""

import json
import logging
import os
import threading
from pathlib import Path

from google.oauth2.credentials import Credentials

from ..config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from .sealed import rozpecet

# Druh zapeceteneho pristupoveho tokenu - musi sedet s auth/oauth_provider.py.
D_PRISTUP = "mcpt"

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
    """Statistiky pouziti. Pristupy uz nedrzi - viz hlavicka souboru."""

    def __init__(self):
        self._lock = threading.Lock()
        # Usage stats: email -> {tool_calls, first_seen, last_seen, errors}
        self._stats: dict[str, dict] = {}
        self._stats_path = TOKEN_STORE_PATH.parent / "mcp-stats.json"
        self._load_stats()

    def poznamenej_prihlaseni(self, email: str):
        """Alias pro track_login - volany z vymeny auth kodu za tokeny."""
        self.track_login(email)

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
            # Denní historie
            day = datetime.now().strftime("%Y-%m-%d")
            daily = self._stats[email].setdefault("daily", {})
            if day not in daily:
                daily[day] = {"calls": 0, "errors": 0}
            daily[day]["calls"] += 1
            if error:
                daily[day]["errors"] += 1
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
                    "daily": s.get("daily", {}),
                })
            return {
                "total_users": total_users,
                "total_tool_calls": total_calls,
                "total_errors": total_errors,
                "users": users,
            }


# Singleton
token_store = TokenStore()


def google_credentials_z_tokenu(mcp_access_token: str) -> Credentials | None:
    """Google credentials z obsahu MCP tokenu; None, kdyz je token cizi nebo stary.

    Refresh token je uvnitr zapecceneho MCP tokenu, takze k jeho ziskani neni
    potreba zadna serverova pamet - a je jedno, ktera instance dotaz obsluhuje.
    """
    udaje = rozpecet(D_PRISTUP, mcp_access_token)
    if not udaje or not udaje.get("g"):
        return None
    return Credentials(
        token=None,
        refresh_token=udaje["g"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=GOOGLE_SCOPES,
    )


def email_z_tokenu(mcp_access_token: str) -> str:
    udaje = rozpecet(D_PRISTUP, mcp_access_token)
    return (udaje or {}).get("e") or "unknown"
