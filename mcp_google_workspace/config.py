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

GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_WORKSPACE_CLIENT_SECRET", "")
