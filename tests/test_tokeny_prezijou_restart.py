"""
Tokeny musí přežít restart instance i běh na druhé instanci.

PROČ TENHLE TEST EXISTUJE. Server běžel na Cloud Runu a držel registrované
klienty, auth kódy a vydané tokeny v paměti instance, mapování na Google tokeny
v `/tmp` jedné instance. Když Cloud Run instanci uspal (nečinnost) nebo přidal
druhou (zátěž), token, který si claude.ai poctivě uložil, už nikdo neznal
a každé volání skončilo `invalid_token`. V Connectors přitom svítila fajfka,
protože ta je o tokenu u klienta, ne o paměti serveru. Proto se tady restart
i druhá instance **hrají**: vyrobí se nový provider (= jiná instance) a ověří,
že token vydaný tím prvním pořád platí.

Spuštění: python -m pytest tests/test_tokeny_prezijou_restart.py -q
"""

import asyncio
import os
import urllib.parse

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("MCP_TOKEN_KEY", Fernet.generate_key().decode())

from mcp.shared.auth import OAuthClientInformationFull  # noqa: E402
from mcp.server.auth.provider import AuthorizationParams  # noqa: E402
from pydantic import AnyUrl  # noqa: E402

from mcp_google_workspace.auth.oauth_provider import GoogleProxyOAuthProvider  # noqa: E402
from mcp_google_workspace.auth import sealed  # noqa: E402
from mcp_google_workspace.auth.token_store import (  # noqa: E402
    google_credentials_z_tokenu,
    email_z_tokenu,
)

REDIRECT = "https://claude.ai/api/mcp/auth_callback"

def _klient(jmeno: str = "claude.ai", metoda: str = "client_secret_post"):
    """Klient pred registraci. `client_id` je zastupne - provider ho pri
    registraci prepise zapecetenou hodnotou. Vyplnuje se proto, ze v mcp 2.x
    je to povinne pole, kdezto ve starsich verzich nebylo."""
    return OAuthClientInformationFull(
        client_id="pred-registraci",
        client_name=jmeno,
        redirect_uris=[AnyUrl(REDIRECT)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method=metoda,
    )

GOOGLE_REFRESH = "1//falesny-google-refresh-token"
EMAIL = "honza@sensio.cz"


def novy_server():
    """Nový provider = jiná instance Cloud Runu (prázdná paměť)."""
    return GoogleProxyOAuthProvider(
        server_url="https://mcp-google-workspace.sensio.cz",
        google_client_id="klient.apps.googleusercontent.com",
        google_client_secret="falesny-secret",
    )


async def _vydej_tokeny(server):
    """Projde celý tok: registrace -> authorize -> Google callback -> tokeny."""
    klient = _klient()
    await server.register_client(klient)

    params = AuthorizationParams(
        state="stav-od-klienta",
        scopes=["mcp:tools"],
        code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        redirect_uri=AnyUrl(REDIRECT),
        redirect_uri_provided_explicitly=True,
        resource=None,
    )
    google_url = await server.authorize(klient, params)
    # `state` je v URL zakódovaný; Google ho serveru vrátí už dekódovaný.
    stav = urllib.parse.unquote(google_url.split("state=")[1].split("&")[0])

    # Google se vrátil na /google/callback se `state`
    cekajici = server.get_pending_auth(stav)
    kod = server.create_auth_code_for_client(
        cekajici["client_id"], cekajici["params"],
        google={"rt": GOOGLE_REFRESH, "e": EMAIL},
    )
    kod_obj = await server.load_authorization_code(klient, kod)
    tokeny = await server.exchange_authorization_code(klient, kod_obj)
    return klient, tokeny


def test_pristupovy_token_plati_i_na_jine_instanci():
    """Jádro věci: token vydaný jednou instancí musí uznat druhá."""
    prvni = novy_server()
    klient, tokeny = asyncio.run(_vydej_tokeny(prvni))

    druha = novy_server()  # jiná instance: nic nezdědila
    nacteny = asyncio.run(druha.load_access_token(tokeny.access_token))
    assert nacteny is not None, "druhá instance token nepoznala - přesně ta stará porucha"
    assert nacteny.scopes == ["mcp:tools"]


def test_klient_zustane_znamy_po_restartu():
    """Registrace přežije, protože client_id JE ta registrace."""
    prvni = novy_server()
    klient, _ = asyncio.run(_vydej_tokeny(prvni))

    druha = novy_server()
    nacteny = asyncio.run(druha.get_client(klient.client_id))
    assert nacteny is not None
    assert str(nacteny.redirect_uris[0]) == REDIRECT


def test_google_pristup_prezije_restart():
    """Skutečný cíl: po restartu se pořád dá sáhnout na Gmail a Drive."""
    prvni = novy_server()
    _, tokeny = asyncio.run(_vydej_tokeny(prvni))

    creds = google_credentials_z_tokenu(tokeny.access_token)
    assert creds is not None and creds.refresh_token == GOOGLE_REFRESH
    assert email_z_tokenu(tokeny.access_token) == EMAIL


def test_obnova_tokenu_funguje_na_jine_instanci():
    prvni = novy_server()
    klient, tokeny = asyncio.run(_vydej_tokeny(prvni))

    druha = novy_server()
    obnova = asyncio.run(druha.load_refresh_token(klient, tokeny.refresh_token))
    assert obnova is not None
    nove = asyncio.run(druha.exchange_refresh_token(klient, obnova, []))
    # Google přístup musí přejít i do obnoveného tokenu, jinak by uživatel
    # po hodině přišel o Gmail, aniž by se odhlásil.
    assert google_credentials_z_tokenu(nove.access_token).refresh_token == GOOGLE_REFRESH


def test_cizi_a_podvrzene_hodnoty_neprojdou():
    server = novy_server()
    assert asyncio.run(server.load_access_token("mcpt_uplne-vymyslene")) is None
    assert asyncio.run(server.get_client("mcpc_vymyslene")) is None
    # Token zapečetěný JINÝM klíčem (jiné nasazení) nesmí projít.
    cizi = sealed.Fernet(sealed.Fernet.generate_key())
    podvrh = "mcpt_" + cizi.encrypt(b'{"g":"ukradeny"}').decode()
    assert asyncio.run(server.load_access_token(podvrh)) is None


def test_token_jednoho_klienta_neplati_druhemu():
    """Otisk klienta v tokenu není ozdoba."""
    server = novy_server()
    klient_a, tokeny = asyncio.run(_vydej_tokeny(server))

    klient_b = _klient("cizi", "none")
    asyncio.run(server.register_client(klient_b))
    assert asyncio.run(server.load_refresh_token(klient_b, tokeny.refresh_token)) is None


def test_prosly_kod_neprojde():
    """Prošlý kód neprojde KVŮLI PLATNOSTI.

    Otisk klienta musí sedět, jinak by tvrzení měřilo jen ten otisk - a mutace,
    která vypne kontrolu platnosti, by prošla zeleně (změřeno 22. 9. 2026).
    """
    from mcp_google_workspace.auth.oauth_provider import otisk_klienta
    server = novy_server()
    klient = _klient("x", "none")
    asyncio.run(server.register_client(klient))

    obsah = {"ch": otisk_klienta(klient.client_id), "ru": REDIRECT, "rp": True, "cc": "x"}
    cerstvy = sealed.zapecet("mcpa", obsah, platnost_s=60)
    assert asyncio.run(server.load_authorization_code(klient, cerstvy)) is not None,         "kontrola: cerstvy kod se spravnym otiskem projit MUSI"

    stary = sealed.zapecet("mcpa", obsah, platnost_s=-1)
    assert asyncio.run(server.load_authorization_code(klient, stary)) is None


def test_druh_hodnoty_se_nesmi_zamenit():
    """Přístupový token není token obnovy ani client_id.

    Bez kontroly druhu by šlo poslat přístupový token jako token obnovy a nechat
    si vydat nový - obojí je zapečetěné tímtéž klíčem, takže rozpečetit by se
    dalo. Druh v hodnotě je jediné, co tomu brání.
    """
    server = novy_server()
    klient, tokeny = asyncio.run(_vydej_tokeny(server))
    assert asyncio.run(server.load_refresh_token(klient, tokeny.access_token)) is None
    assert asyncio.run(server.load_access_token(tokeny.refresh_token)) is None
    assert asyncio.run(server.get_client(tokeny.access_token)) is None


def test_bez_klice_server_nepecetni():
    """Fail-closed: bez MCP_TOKEN_KEY se nic nezapečetí, místo tichého klíče."""
    puvodni, sifra = os.environ.get("MCP_TOKEN_KEY"), sealed._fernet
    os.environ.pop("MCP_TOKEN_KEY", None)
    sealed._fernet = None
    try:
        assert sealed.klic_je() is False
        with pytest.raises(sealed.ChybiKlic):
            sealed.zapecet("mcpt", {"a": 1})
    finally:
        if puvodni:
            os.environ["MCP_TOKEN_KEY"] = puvodni
        sealed._fernet = sifra


def test_prepsana_predpona_neprojde():
    """Druh se bere ZEVNITŘ, ne z předpony.

    Nezávislý review 22. 9. 2026 změřil proti skutečnému `/token`, že stačilo
    přejmenovat `mcpa_` na `mcpr_` a auth kód posloužil jako token obnovy -
    Fernet podepisuje obsah, ne text před ním. Tenhle test tu cestu hlídá.
    """
    server = novy_server()
    klient, tokeny = asyncio.run(_vydej_tokeny(server))

    def prejmenuj(hodnota: str, novy_druh: str) -> str:
        return novy_druh + "_" + hodnota.split("_", 1)[1]

    # přístupový token převlečený za token obnovy a naopak
    assert asyncio.run(server.load_refresh_token(klient, prejmenuj(tokeny.access_token, "mcpr"))) is None
    assert asyncio.run(server.load_access_token(prejmenuj(tokeny.refresh_token, "mcpt"))) is None
    # a registrace klienta převlečená za token
    assert asyncio.run(server.load_access_token(prejmenuj(klient.client_id, "mcpt"))) is None


def test_registrace_si_pamatuje_client_secret():
    """Klient s metodou client_secret_post musí dostat svůj secret zpátky.

    Bez toho vrátí `/token` `invalid_client`: SDK secret při registraci vydá,
    ale server by ho po restartu (a vlastně hned) neznal.
    """
    server = novy_server()
    klient = _klient("s tajemstvim", "client_secret_post")
    klient.client_secret = "tajemstvi-od-sdk"
    klient.client_secret_expires_at = 0
    asyncio.run(server.register_client(klient))

    nacteny = asyncio.run(novy_server().get_client(klient.client_id))
    assert nacteny is not None and nacteny.client_secret == "tajemstvi-od-sdk"


def test_retez_obnovy_neprodluzuje_pristup_donekonecna():
    """Obnova nesmí posouvat konec platnosti pořád dál.

    Jinak by držitel uniklého tokenu obnovy prodlužoval přístup navždy.
    Měří se přes obsah tokenu: konec je vázaný na začátek řetězu, ne na teď.
    """
    from mcp_google_workspace.auth.oauth_provider import REFRESH_TOKEN_TTL
    server = novy_server()
    klient, tokeny = asyncio.run(_vydej_tokeny(server))

    prvni = sealed.rozpecet("mcpr", tokeny.refresh_token)
    obnova = asyncio.run(server.load_refresh_token(klient, tokeny.refresh_token))
    nove = asyncio.run(server.exchange_refresh_token(klient, obnova, []))
    druhy = sealed.rozpecet("mcpr", nove.refresh_token)

    assert druhy["rt0"] == prvni["rt0"], "zacatek retezu se nesmi posouvat"

    # A TED TO PODSTATNE: retez, ktery uz skoro dobehl. Bez tohohle by tvrzeni
    # merilo jen to, ze se dve hodnoty spocitaly v teze vterine - mutace, ktera
    # zacatek retezu resetuje na "ted", prosla zelene (zmereno 22. 9. 2026).
    import time as _t
    from mcp_google_workspace.auth.oauth_provider import otisk_klienta
    # Zbyva DESET MINUT, ne hodina: pri hodine by se nepoznalo, ze se pristupovy
    # token (TTL take hodina) neomezil na zbytek retezu.
    stary_zacatek = int(_t.time()) - (REFRESH_TOKEN_TTL - 600)
    stary = sealed.zapecet("mcpr", {
        "ch": otisk_klienta(klient.client_id), "sc": ["mcp:tools"],
        "g": GOOGLE_REFRESH, "e": EMAIL, "rt0": stary_zacatek,
    }, platnost_s=600)
    obnova2 = asyncio.run(server.load_refresh_token(klient, stary))
    nove2 = asyncio.run(server.exchange_refresh_token(klient, obnova2, []))
    obsah2 = sealed.rozpecet("mcpr", nove2.refresh_token)
    assert obsah2["rt0"] == stary_zacatek
    assert obsah2["exp"] <= stary_zacatek + REFRESH_TOKEN_TTL + 1, (
        "obnova posunula konec platnosti za hranici prvniho prihlaseni")
    assert nove2.expires_in <= 600, "ohlasena platnost nesmi prezit retez"
    # A TOTEZ UVNITR TOKENU, ne jen v ohlasene hodnote: mutace, ktera zkratila
    # jen `expires_in` a token nechala platit hodinu, prosla zelene.
    obsah_pristup = sealed.rozpecet("mcpt", nove2.access_token)
    assert obsah_pristup["exp"] <= stary_zacatek + REFRESH_TOKEN_TTL + 1, (
        "pristupovy token plati dele nez retez, ze ktereho vznikl")


def test_clovek_ma_na_prihlaseni_ke_googlu_vic_nez_minutu():
    """`state` čeká na ČLOVĚKA, auth kód jen na stroj.

    Když obě hodnoty sdílely jednu konstantu, zkrácení kódu na minutu zkrátilo
    i okno na výběr účtu, heslo a dvoufázové ověření - konektor pak končil
    hláškou "Invalid or expired state". Změřeno nezávislým reviewem
    22. 9. 2026: po 61 s už to neprošlo.
    """
    from mcp_google_workspace.auth.oauth_provider import STAV_TTL, AUTH_CODE_TTL
    assert STAV_TTL >= 300, "na přihlášení ke Googlu musí být aspoň pět minut"
    assert AUTH_CODE_TTL <= STAV_TTL

    server = novy_server()
    klient = _klient()
    asyncio.run(server.register_client(klient))
    params = AuthorizationParams(
        state="s", scopes=["mcp:tools"], code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        redirect_uri=AnyUrl(REDIRECT), redirect_uri_provided_explicitly=True, resource=None,
    )
    url = asyncio.run(server.authorize(klient, params))
    stav = urllib.parse.unquote(url.split("state=")[1].split("&")[0])
    obsah = sealed.rozpecet("mcps", stav)
    zbyva = obsah["exp"] - obsah["iat"]
    assert zbyva >= 300, f"na přihlášení zbývá jen {zbyva} s"


def test_vyprseny_retez_je_invalid_grant_ne_pad():
    """Překročený strop řetězu musí být chyba OAuth, ne HTTP 500."""
    from mcp.server.auth.provider import TokenError
    from mcp_google_workspace.auth.oauth_provider import otisk_klienta, REFRESH_TOKEN_TTL
    import time as _t

    server = novy_server()
    klient = _klient()
    asyncio.run(server.register_client(klient))
    vyprsely = sealed.zapecet("mcpr", {
        "ch": otisk_klienta(klient.client_id), "sc": ["mcp:tools"],
        "g": GOOGLE_REFRESH, "e": EMAIL, "rt0": int(_t.time()) - REFRESH_TOKEN_TTL,
    }, platnost_s=60)
    obnova = asyncio.run(server.load_refresh_token(klient, vyprsely))
    with pytest.raises(TokenError):
        asyncio.run(server.exchange_refresh_token(klient, obnova, []))


def test_v_http_rezimu_se_nepada_na_schranku_majitele_serveru():
    """Token bez Google údajů nesmí vést na env credentials majitele serveru.

    Jinak by přihlášený cizí uživatel dostal do ruky cizí poštu. Původní
    pojistka se testovala až po načtení proměnné, takže nechránila (změřeno
    reviewem 22. 9. 2026).
    """
    from mcp_google_workspace.auth import context

    class FalesnyToken:
        token = "mcpt_bez-google-udaju"

    puvodni = os.environ.get("MCP_TRANSPORT")
    os.environ["MCP_TRANSPORT"] = "streamable-http"
    try:
        context.get_access_token = lambda: FalesnyToken()
        with pytest.raises(PermissionError):
            context.get_current_google_credentials()
    finally:
        if puvodni is None:
            os.environ.pop("MCP_TRANSPORT", None)
        else:
            os.environ["MCP_TRANSPORT"] = puvodni
