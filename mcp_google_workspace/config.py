import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "mcp-google"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"

# OAuth Client ID - verejny identifikator aplikace (ne secret)
# Pouziva se s PKCE flow - zadny Client Secret neni potreba
GOOGLE_CLIENT_ID = os.environ.get(
    "GOOGLE_WORKSPACE_CLIENT_ID",
    "581084999054-tt8lg3fgp975ohh8abgvivo57tgupimp.apps.googleusercontent.com",
)

# CLIENT SECRET SE NEZAPISUJE DO KODU. Do 22. 9. 2026 tu stala jako vychozi
# hodnota skutecna hodnota secretu desktopoveho klienta "Sensio MCP" - a tenhle
# repozitar je verejny, takze byla od 20. 3. 2026 na ocich komukoliv. U
# desktopoveho (installed) klienta ji Google za tajemstvi nepovazuje a PKCE ji
# nepotrebuje (viz komentar u GOOGLE_CLIENT_ID vys), presto nema v kodu co delat.
#
# Produkcni web klient na Cloud Runu bere secret z prostredi uz ted; prazdna
# hodnota je proto v poradku pro lokalni PKCE beh a chybu nahlasi az ten, kdo
# secret opravdu potrebuje (vymena Google auth kodu v server.py).
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_WORKSPACE_CLIENT_SECRET", "")
