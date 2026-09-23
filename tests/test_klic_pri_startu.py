"""
Bez `MCP_TOKEN_KEY` nesmí HTTP režim nastartovat.

PROČ TENHLE TEST EXISTUJE. `docs/nasazeni-a-klice.md` tvrdilo, že bez klíče
server **nenastartuje**. Nezávislý review 23. 9. 2026 změřil, že to nebyla
pravda: proces naběhl, `/.well-known/oauth-authorization-server` vracel 200
a rozbilo se to až uživateli na `POST /register` chybou 500 bez vysvětlení.
Nasazení přitom bylo zelené, takže se o tom nikdo nedozvěděl, dokud se někdo
nezkusil připojit.

Příčina: `klic_je()` bylo v `server.py` naimportované, ale nikde se nevolalo,
a `__main__.py` žádnou kontrolu neměl. Komentář v kódu odkazoval na kontrolu,
která neexistovala.

Spuštění: python -m pytest tests/test_klic_pri_startu.py -q
"""

import os
import subprocess
import sys

import pytest

PRIKAZ = [sys.executable, "-c", "from mcp_google_workspace.__main__ import main; main()"]


def _spust(prostredi: dict, cekej_s: int = 25) -> subprocess.CompletedProcess:
    p = dict(os.environ)
    for k in ("MCP_TOKEN_KEY", "MCP_TRANSPORT"):
        p.pop(k, None)
    p.update(prostredi)
    return subprocess.run(
        PRIKAZ, env=p, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=cekej_s,
    )


def test_http_rezim_bez_klice_skonci_a_rekne_proc():
    r = _spust({"MCP_TRANSPORT": "streamable-http"})
    vystup = r.stdout + r.stderr

    assert r.returncode != 0, "bez klíče nesmí server běžet dál"
    assert "MCP_TOKEN_KEY" in vystup, (
        "hláška musí jmenovat proměnnou, jinak člověk neví, co doplnit"
    )
    assert "docs/nasazeni-a-klice.md" in vystup, "a kde se to nastavuje"


def test_stdio_rezim_klic_nepotrebuje():
    """Pozitivní kontrola: kontrola nesmí rozbít lokální běh.

    Bez tohohle by tvrzení výš prošlo i pro bránu, která klíč vyžaduje vždycky -
    a tím by rozbila každé lokální použití, kde se žádné MCP tokeny nevydávají.
    Stdio server čeká na vstup, takže se měří tím, že **nespadne** do timeoutu
    vlastní hláškou o chybějícím klíči.
    """
    try:
        r = _spust({"MCP_TRANSPORT": "stdio"}, cekej_s=15)
    except subprocess.TimeoutExpired:
        return  # běží a čeká na vstup - přesně co chceme

    vystup = r.stdout + r.stderr
    assert "MCP_TOKEN_KEY" not in vystup, (
        f"stdio běh na klíči padnout nesmí, ale spadl:\n{vystup[-600:]}"
    )


def test_http_rezim_s_klicem_na_klici_nespadne():
    """Druhá pozitivní kontrola: s klíčem musí brána pustit dál."""
    from cryptography.fernet import Fernet

    try:
        r = _spust({
            "MCP_TRANSPORT": "streamable-http",
            "MCP_TOKEN_KEY": Fernet.generate_key().decode(),
            "PORT": "8123",
        }, cekej_s=15)
    except subprocess.TimeoutExpired:
        return  # server běží - přesně co chceme

    vystup = r.stdout + r.stderr
    assert "Chybi MCP_TOKEN_KEY" not in vystup, (
        f"s platným klíčem brána zastavit nesmí:\n{vystup[-600:]}"
    )
