import json
import os
from pathlib import Path
from google.oauth2.credentials import Credentials

from ..config import CREDENTIALS_FILE, GOOGLE_CLIENT_ID


def load_credentials(creds_file: Path = CREDENTIALS_FILE) -> dict | None:
    """Nacte ulozene credentials ze souboru."""
    if not creds_file.exists():
        return None
    with open(creds_file) as f:
        return json.load(f)


def save_credentials(creds_file: Path = CREDENTIALS_FILE, **kwargs) -> None:
    """Ulozi credentials do souboru."""
    creds_file.parent.mkdir(parents=True, exist_ok=True)
    with open(creds_file, "w") as f:
        json.dump(kwargs, f, indent=2)


def get_google_credentials() -> Credentials:
    """Ziska Google credentials - z env, souboru, nebo spusti PKCE OAuth flow."""
    client_id = GOOGLE_CLIENT_ID
    # client_secret pro zpetnou kompatibilitu s existujicimi tokeny
    client_secret = os.environ.get("GOOGLE_WORKSPACE_CLIENT_SECRET", "")

    # 1. Zkusit env promenne (zpetna kompatibilita)
    refresh_token = os.environ.get("GOOGLE_WORKSPACE_REFRESH_TOKEN")
    if refresh_token:
        return Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )

    # 2. Zkusit lokalni soubor
    saved = load_credentials()
    if saved and saved.get("refresh_token"):
        return Credentials(
            token=None,
            refresh_token=saved["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=saved.get("client_id", client_id),
            client_secret=saved.get("client_secret", ""),
        )

    # 3. Spustit PKCE OAuth flow - otevre prohlizec
    from .oauth_flow import run_oauth_flow
    token_data = run_oauth_flow()
    save_credentials(
        refresh_token=token_data["refresh_token"],
        client_id=client_id,
    )
    return Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret="",
    )
