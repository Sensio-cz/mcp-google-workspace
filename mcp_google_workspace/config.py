import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "mcp-google"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"

# OAuth Client ID - verejny identifikator aplikace (ne secret).
#
# POZOR, PKCE SAMO O SOBE GOOGLU NESTACI. Drive tu stalo, ze s PKCE zadny
# Client Secret neni potreba; zmereno 23. 9. 2026 proti skutecnemu
# oauth2.googleapis.com/token to neplati ani u tohohle desktopoveho klienta:
# vymena kodu i obnova tokenu bez secretu konci `400 invalid_request:
# client_secret is missing`. PKCE je u Googlu obrana NAVIC, ne nahrada.
GOOGLE_CLIENT_ID = os.environ.get(
    "GOOGLE_WORKSPACE_CLIENT_ID",
    "581084999054-tt8lg3fgp975ohh8abgvivo57tgupimp.apps.googleusercontent.com",
)

# CLIENT SECRET SE NEZAPISUJE DO KODU. Do 22. 9. 2026 tu stala jako vychozi
# hodnota skutecna hodnota secretu desktopoveho klienta "Sensio MCP" - a tenhle
# repozitar je verejny, takze byla od 20. 3. 2026 na ocich komukoliv. U
# desktopoveho (installed) klienta ji Google za tajemstvi nepovazuje, presto
# nema v kodu co delat.
#
# PRAZDNA HODNOTA NENI PROVOZUSCHOPNY STAV. Drive tu stalo, ze pro lokalni PKCE
# beh je v poradku; neni - Google secret vyzaduje i pri PKCE (mereni u
# GOOGLE_CLIENT_ID vys). Lokalni prihlaseni proto bez teto promenne odmitne
# zacit (auth/oauth_flow.py) a vzdaleny beh na Cloud Runu ji bere z prostredi.
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_WORKSPACE_CLIENT_SECRET", "")
