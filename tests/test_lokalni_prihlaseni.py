"""
Lokální přihlášení ke Googlu: PKCE **i** client secret, a poctivé selhání.

PROČ TENHLE TEST EXISTUJE. Kód o sobě tvrdil, že lokální flow vyměňuje auth kód
za token „pomocí PKCE (bez client_secret)" a že s PKCE žádný secret potřeba
není. Změřeno 23. 9. 2026 proti skutečnému `oauth2.googleapis.com/token`
to neplatí ani u desktopového (installed) klienta:

    výměna kódu bez secretu   -> 400 invalid_request: client_secret is missing.
    obnova tokenu bez secretu -> 400 invalid_request: client_secret is missing.

Původní kód se navíc rozhodoval **buď - anebo**: když byl secret nastavený,
`code_challenge` se do žádosti vůbec nedal. Takže jediná větev, která u Googlu
fungovala, byla zároveň ta bez PKCE. Tenhle test drží obojí pohromadě: PKCE se
posílá vždy a bez secretu se flow ani nerozjede.

Spuštění: python -m pytest tests/test_lokalni_prihlaseni.py -q
"""

import base64
import hashlib
import urllib.parse

import pytest

from mcp_google_workspace.auth import oauth_flow


class FalesnyServer:
    """Náhrada za HTTPServer: nesahá na síť a hned se vrátí.

    Používají ho OBA testy, které volají `run_oauth_flow()`, i ten, kde se flow
    má zastavit hned na začátku. Změřeno mutací: bez téhle náhrady trvá běh se
    zrušenou bránou 120 sekund (skutečný socket čeká na `server.timeout`),
    takže by se regrese projevila jako zaseknutý test, ne jako spadlé tvrzení.
    """

    server_address = ("localhost", 1234)
    timeout = 0

    def __init__(self, *a, **kw):
        pass

    def handle_request(self):
        pass  # nikdo se nevrátí, flow pak skončí chybou o chybějícím tokenu

    def server_close(self):
        pass


def test_code_challenge_je_opravdu_s256_verifieru():
    """Pozitivní kontrola: challenge musí jít z verifieru spočítat.

    Bez tohohle by ostatní tvrzení prošla i s náhodným řetězcem místo hashe.
    """
    verifier, challenge = oauth_flow._generate_pkce()

    ocekavany = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")

    assert challenge == ocekavany
    assert "=" not in challenge, "padding musí být odříznutý"
    assert 43 <= len(verifier) <= 128, "RFC 7636 povoluje 43-128 znaků"


def test_auth_params_nesou_pkce():
    p = oauth_flow.sestav_auth_params("id-klienta", "http://localhost:1234", "vyzva")

    assert p["code_challenge"] == "vyzva"
    assert p["code_challenge_method"] == "S256"
    assert p["access_type"] == "offline", "bez toho nepřijde refresh token"


def test_token_params_nesou_verifier_i_secret():
    p = oauth_flow.sestav_token_params(
        code="kod", client_id="id-klienta", redirect_uri="http://localhost:1234",
        code_verifier="tajny-verifier", client_secret="secret-klienta",
    )

    assert p["code_verifier"] == "tajny-verifier"
    assert p["client_secret"] == "secret-klienta"
    assert p["grant_type"] == "authorization_code"


def test_token_params_bez_secretu_porad_nesou_verifier():
    """Prázdný secret nesmí odnést PKCE s sebou - to byla ta původní záměna."""
    p = oauth_flow.sestav_token_params(
        code="kod", client_id="id-klienta", redirect_uri="http://localhost:1234",
        code_verifier="tajny-verifier", client_secret="",
    )

    assert p["code_verifier"] == "tajny-verifier"
    assert "client_secret" not in p


def test_bez_secretu_se_prohlizec_vubec_neotevre(monkeypatch):
    """Uživatel se to musí dozvědět dřív, než proklikne souhlas se šesti scopy."""
    otevreno = []
    monkeypatch.setattr(oauth_flow, "GOOGLE_CLIENT_SECRET", "")
    monkeypatch.setattr(oauth_flow.http.server, "HTTPServer", FalesnyServer)
    monkeypatch.setattr(oauth_flow.webbrowser, "open", lambda url: otevreno.append(url))

    with pytest.raises(RuntimeError) as chyba:
        oauth_flow.run_oauth_flow()

    assert "GOOGLE_WORKSPACE_CLIENT_SECRET" in str(chyba.value), (
        "hláška musí jmenovat proměnnou, jinak uživatel neví, co doplnit"
    )
    assert otevreno == [], "bez secretu nemá smysl otevírat prohlížeč"


def test_se_secretem_jde_do_prohlizece_url_s_pkce(monkeypatch):
    """Pozitivní kontrola celého sestavení: PKCE jde ven i KDYŽ je secret.

    Tohle je to vlastní měření regrese. Kdyby se `code_challenge` zase schoval
    za podmínku `if not GOOGLE_CLIENT_SECRET`, projdou všechna tvrzení výš
    (ta sahají na čisté funkce) a spadne jenom tohle.
    """
    otevreno = []

    monkeypatch.setattr(oauth_flow, "GOOGLE_CLIENT_SECRET", "secret-klienta")
    monkeypatch.setattr(oauth_flow.http.server, "HTTPServer", FalesnyServer)
    monkeypatch.setattr(oauth_flow.webbrowser, "open", lambda url: otevreno.append(url))

    with pytest.raises(RuntimeError) as chyba:
        oauth_flow.run_oauth_flow()

    assert "refresh token" in str(chyba.value), (
        "flow měl dojít až za přihlašovací obrazovku, ne spadnout na chybějícím secretu"
    )
    assert len(otevreno) == 1
    dotaz = urllib.parse.parse_qs(urllib.parse.urlparse(otevreno[0]).query)
    assert dotaz["code_challenge_method"] == ["S256"]
    assert dotaz["code_challenge"][0], "PKCE musí jít ven i se secretem"
