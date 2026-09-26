"""
Nástroj musí vidět token AKTUÁLNÍHO požadavku, ne prvního požadavku relace.

PROČ TENHLE TEST EXISTUJE. Ve stavovém režimu streamable HTTP spustí SDK
zpracování relace v úloze založené prvním požadavkem a `get_access_token()`
pak v nástrojích vrací token toho prvního požadavku. Klient po hodině token
obnoví, middleware nový token přijme, ale nástroj pořád čte původní, už
propadlý - a každé volání Gmailu končí hláškou „Tenhle MCP token nenese Google
přístup“. Konektor přitom svítí jako připojený. Změřeno 26. 9. 2026 na
produkci (dvakrát, vždy zhruba hodinu po přihlášení) a v reprodukci: v jedné
relaci poslán token 1 a pak token 2, nástroj viděl dvakrát token 1.

Test proto posílá přes skutečnou HTTP aplikaci dva různé tokeny a ověřuje,
že nástroj pokaždé vidí ten, který přišel.

Spuštění: python -m pytest tests/test_token_aktualniho_pozadavku.py -q
"""

import json
import os

from cryptography.fernet import Fernet

os.environ.setdefault("MCP_TOKEN_KEY", Fernet.generate_key().decode())
os.environ.setdefault("MCP_SERVER_URL", "https://testserver")

from starlette.testclient import TestClient  # noqa: E402
from mcp.server.auth.middleware.auth_context import get_access_token  # noqa: E402

from mcp_google_workspace import server as srv  # noqa: E402
from mcp_google_workspace.auth.sealed import zapecet  # noqa: E402


@srv.mcp.tool()
async def _test_kdo_jsem() -> str:
    """Jen pro test: vrátí konec tokenu, který nástroj vidí."""
    token = get_access_token()
    return token.token[-16:] if token else "zadny"


def _token(email: str) -> str:
    return zapecet(
        "mcpt",
        {"ch": "x", "sc": ["mcp:tools"], "g": f"1//rt-{email}", "e": email, "r": None},
        platnost_s=3600,
    )


def _hlavicky(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "mcp-protocol-version": "2025-06-18",
    }


def _videny_token(odpoved: str) -> str:
    """Z odpovědi (JSON nebo SSE) vytáhne text, který vrátil nástroj."""
    for radek in odpoved.splitlines():
        radek = radek.removeprefix("data:").strip()
        if radek.startswith("{"):
            return json.loads(radek)["result"]["content"][0]["text"]
    raise AssertionError(f"Odpověď bez výsledku: {odpoved[:300]}")


def test_nastroj_vidi_token_aktualniho_pozadavku():
    prvni, druhy = _token("prvni@example.com"), _token("druhy@example.com")
    with TestClient(srv.mcp.streamable_http_app(), base_url=srv.SERVER_URL) as klient:
        init = klient.post("/mcp", headers=_hlavicky(prvni), json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "1"}},
        })
        assert init.status_code == 200
        relace = init.headers.get("mcp-session-id")

        for token in (prvni, druhy):
            hlavicky = _hlavicky(token)
            if relace:
                hlavicky["mcp-session-id"] = relace
            odpoved = klient.post("/mcp", headers=hlavicky, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "_test_kdo_jsem", "arguments": {}},
            })
            assert odpoved.status_code == 200, odpoved.text[:300]
            assert _videny_token(odpoved.text) == token[-16:]
