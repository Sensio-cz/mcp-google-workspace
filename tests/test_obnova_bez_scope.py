"""Obnova Google tokenu nesmi posilat scopes (0.3.3).

google-auth pri `Credentials.refresh` prida do pozadavku `scope=...`, kdyz jsou scopes
vyplnene; Google pak vrati `invalid_scope`, pokud puvodni souhlas uzivatele ten rozsah
nemel. Po rozsireni GOOGLE_SCOPES o calendar.events (0.3.2) tak 10. 10. 2026 prestala
fungovat vsechna starsi prihlaseni, dokud se uzivatel neprihlasil znovu.
"""
import os

os.environ.setdefault("MCP_TOKEN_SECRET", "x" * 32)

from mcp_google_workspace.auth import sealed, token_store as ts


def test_credentials_z_tokenu_nemaji_scopes():
    token = sealed.zapecet(ts.D_PRISTUP, {"g": "1//refresh", "e": "a@b.cz"}, platnost_s=600)
    creds = ts.google_credentials_z_tokenu(token)
    assert creds is not None
    assert creds.refresh_token == "1//refresh"
    assert creds.scopes is None, "scopes v Credentials = google-auth posle scope pri obnove = invalid_scope pro starsi souhlasy"


def test_cizi_token_vrati_none():
    assert ts.google_credentials_z_tokenu("neco") is None
