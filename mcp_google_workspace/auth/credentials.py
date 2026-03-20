import json
import os
import threading
from pathlib import Path
from google.oauth2.credentials import Credentials

from ..config import CREDENTIALS_FILE, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET


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


# Background OAuth flow state
_oauth_lock = threading.Lock()
_oauth_result: dict | None = None
_oauth_error: str | None = None
_oauth_done = threading.Event()


def _run_oauth_background():
    """Spusti OAuth flow v background threadu."""
    global _oauth_result, _oauth_error
    try:
        from .oauth_flow import run_oauth_flow
        token_data = run_oauth_flow()
        save_credentials(
            refresh_token=token_data["refresh_token"],
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
        )
        _oauth_result = token_data
    except Exception as e:
        _oauth_error = str(e)
    finally:
        _oauth_done.set()


def _start_oauth_if_needed():
    """Spusti OAuth flow na pozadi pokud jeste nebezi."""
    with _oauth_lock:
        if not _oauth_done.is_set() and not hasattr(_start_oauth_if_needed, "_started"):
            _start_oauth_if_needed._started = True
            t = threading.Thread(target=_run_oauth_background, daemon=True)
            t.start()


def get_google_credentials() -> Credentials:
    """Ziska Google credentials - z env, souboru, nebo spusti PKCE OAuth flow."""
    client_id = GOOGLE_CLIENT_ID
    client_secret = GOOGLE_CLIENT_SECRET

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
            client_secret=saved.get("client_secret", client_secret),
        )

    # 3. Na remote serveru - chyba (kazdy user se prihlasi pres OAuth connector)
    if os.environ.get("MCP_TRANSPORT") == "streamable-http":
        raise RuntimeError("Chybi Google credentials. Kazdy uzivatel se musi prihlasit pres OAuth.")

    # 4. Lokalne - spustit OAuth na pozadi a vratit auth URL
    _start_oauth_if_needed()

    # Pokud uz OAuth dobehlo (rychle), pouzit vysledek
    if _oauth_done.wait(timeout=2):
        if _oauth_error:
            raise RuntimeError(f"Prihlaseni selhalo: {_oauth_error}")
        if _oauth_result:
            return Credentials(
                token=_oauth_result.get("access_token"),
                refresh_token=_oauth_result["refresh_token"],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
            )

    # OAuth jeste probiha - vratit URL pro uzivatele
    from .oauth_flow import get_pending_auth_url
    auth_url = get_pending_auth_url()
    if auth_url:
        raise RuntimeError(
            f"Prihlaste se ke Google uctu kliknutim na tento odkaz:\n\n{auth_url}\n\n"
            "Po prihlaseni zkuste pozadavek znovu."
        )

    raise RuntimeError("OAuth flow se nespustil. Zkuste restartovat VS Code.")
