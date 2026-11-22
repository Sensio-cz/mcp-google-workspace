"""Rezim vratneho: pristup ke Googlu pres vratneho Stáze v pracovne Red Dwarfu.

ZAPINA HO JEN PROMENNA `GOOGLE_WORKSPACE_GATE_URL` (napr. `http://trezor:8767/_osoba`).
Bez ni se tenhle modul ani nenaimportuje (`__main__.py`) a server se chova jako
driv - sluzba Sensia na Cloud Runu ji nema a nesmi se pro ni nic zmenit.

PROC: v pracovne nema lezet zadny token Googlu. Obnovovaci token drzi admin Red Dwarfu,
hodinovy token si u nej rekne vratny a prilozi ho k pozadavku sam. Server v pracovne
proto nema vlastni prihlaseni, necte `GOOGLE_WORKSPACE_*_SECRET` ani `~/.config/mcp-google/`
a nesaha na `googleapis.com` ani `accounts.google.com` - kazde volani jde na vratneho:

    <GATE_URL>/<ucet>/<sluzba>/<cesta Googlu>      sluzba = gmail | drive | calendar

S HLAVICKAMI (kontrakt C4):
    Authorization: Bearer <token pracovny>          soubor GOOGLE_WORKSPACE_GATE_TOKEN_FILE
                                                    (vychozi /run/secrets/trezor-token)
    X-Kryton-Proof: <users_id>.<ts>.<mac>           klic pracovny GOOGLE_WORKSPACE_GATE_KEY_FILE
                                                    (vychozi /run/secrets/workspace-key)

DUKAZ (kontrakt C3) vratny jen preposle adminu; overit ho umi jen admin, protoze klic
pracovny vratny nema - ovladnuty vratny si tak nerekne o token cloveka, jehoz pracovna
prave nevola:
    K   = HKDF-SHA256(ikm = obsah souboru klice BEZE ZMENY, salt prazdna, info "kryton-person-token-v1", 32 B)
    mac = hex(HMAC-SHA256(K, "<users_id>\\n<ts>\\n<ucel>\\n<ucet>"))
    ucel = "person-token" pro data uctu, "person-accounts" (s prazdnym uctem) pro `_seznam`
    ts = cele sekundy, okno +-60 s; klient ho pocita PRI KAZDEM POZADAVKU.

TOKEN A KLIC SE CTOU ZE SOUBORU PRI KAZDEM POZADAVKU, ne pri startu: rotace tokenu
pracovny nebo klice pracovny tak nevyzaduje restart MCP serveru (a server nedrzi kopii
v pameti dele, nez je nutne).

HKDF je tu ze standardni knihovny (RFC 5869, jeden blok, protoze 32 B = delka SHA-256):
prazdna sul je u HMAC totez co 32 nulovych bajtu, presne jako `crypto.hkdfSync` v Node.
Vektor v `tests/test_rezim_vratneho.py` je spocitany v Node, nezavisle.

POJISTKA NA STRANE KLIENTA: `GateHttp` odmitne kazdy pozadavek na adresu, ktera nezacina
`<GATE_URL>/<ucet>/`. Knihovna Googlu umi adresu zmenit sama: `MediaIoBaseDownload` prejde
na `Content-Location` z odpovedi a nahravani (`/upload/`) zahodi cestu za hostitelem
(zmereno v S1, `.relay/gst-r253-s1-mereni.md` v Red Dwarfu). Token pracovny tak nikdy
neodejde nikam jinam nez k vratnemu.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import re
import socket
import threading
import time
import urllib.parse
from pathlib import Path

import httplib2

GATE_URL_ENV = "GOOGLE_WORKSPACE_GATE_URL"
TOKEN_FILE_ENV = "GOOGLE_WORKSPACE_GATE_TOKEN_FILE"
KEY_FILE_ENV = "GOOGLE_WORKSPACE_GATE_KEY_FILE"
USERS_ID_ENV = "KRYTON_UCTY_USERS_ID"
VYCHOZI_TOKEN = "/run/secrets/trezor-token"
VYCHOZI_KLIC = "/run/secrets/workspace-key"

HKDF_INFO = b"kryton-person-token-v1"
UCEL_TOKEN = "person-token"
UCEL_SEZNAM = "person-accounts"

UCET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
USERS_ID_RE = re.compile(r"^[1-9][0-9]{0,15}$")

PRIPOJ = "kryton-ucty pripoj google --jmeno {ucet}"

# Kam ktera sluzba miri: api_endpoint knihovny nahradi CELY rootUrl + servicePath,
# takze u Disku a kalendare musi zaklad nest i verzi API (zmereno v S1).
SLUZBY = {
    ("gmail", "v1"): ("gmail", ""),
    ("drive", "v3"): ("drive", "drive/v3/"),
    ("calendar", "v3"): ("calendar", "calendar/v3/"),
}

TIMEOUT_S = 60
SEZNAM_PLATNOST_S = 60


class GateError(Exception):
    """Chyba rezimu vratneho s kodem a vetou pro cloveka (vraci ji nastroj)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --- konfigurace (cte se pri kazdem volani) ----------------------------------

def gate_url() -> str:
    """Zaklad vratneho bez lomitka na konci. Neplatna hodnota = chyba, nikdy navrat k Googlu."""
    raw = os.environ.get(GATE_URL_ENV)
    if raw is None:
        raise GateError("GATE_URL_MISSING", f"Chybí proměnná {GATE_URL_ENV}.")
    url = raw.strip().rstrip("/")
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.netloc or p.query or p.fragment or "@" in p.netloc:
        raise GateError(
            "GATE_URL_INVALID",
            # Hodnotu nevypisovat: adresa s user:heslo@ by heslo dala do chyby a logu (revize A).
            f"Proměnná {GATE_URL_ENV} musí být adresa vrátného bez přihlašovacích údajů, "
            "např. http://trezor:8767/_osoba.",
        )
    return url


def _cti_soubor(env: str, vychozi: str, kod: str, co: str) -> bytes:
    cesta = os.environ.get(env) or vychozi
    try:
        return Path(cesta).read_bytes()
    except OSError:
        raise GateError(
            kod,
            f"Nejde přečíst {co} ({cesta}). Pracovna asi nemá Stázi nebo je potřeba ji znovu vytvořit; "
            "napiš správci Red Dwarfu.",
        ) from None


def nacti_token() -> str:
    token = _cti_soubor(TOKEN_FILE_ENV, VYCHOZI_TOKEN, "GATE_TOKEN_MISSING", "token Stáze").decode("utf-8", "replace").strip()
    if not token or any(c.isspace() for c in token):
        raise GateError("GATE_TOKEN_MISSING", "Token Stáze je prázdný nebo poškozený; napiš správci Red Dwarfu.")
    return token


def nacti_klic() -> bytes:
    # BEZE ZMENY: klic je 97 znaku bez konce radku (admin/lib/workspace-proof.js v Red Dwarfu);
    # orezanim by klient spocital jiny klic nez admin.
    klic = _cti_soubor(KEY_FILE_ENV, VYCHOZI_KLIC, "GATE_KEY_MISSING", "klíč pracovny")
    if not klic:
        raise GateError("GATE_KEY_MISSING", "Klíč pracovny je prázdný; napiš správci Red Dwarfu.")
    return klic


def users_id() -> str:
    """Id osoby: KRYTON_UCTY_USERS_ID, jinak zaznam ~/.config/kryton/ucty.json (pise ho instalace)."""
    raw = os.environ.get(USERS_ID_ENV)
    if not raw:
        zaznam = Path.home() / ".config" / "kryton" / "ucty.json"
        try:
            raw = json.loads(zaznam.read_text()).get("users_id")
        except (OSError, ValueError, AttributeError):
            raw = None
    hodnota = str(raw).strip() if raw is not None else ""
    if not USERS_ID_RE.fullmatch(hodnota):
        raise GateError(
            "USERS_ID_MISSING",
            f"Nevím, čí je pracovna: chybí {USERS_ID_ENV} i ~/.config/kryton/ucty.json. Napiš správci Red Dwarfu.",
        )
    return hodnota


def over_ucet(ucet: str) -> str:
    if not isinstance(ucet, str) or not UCET_RE.fullmatch(ucet):
        raise GateError(
            "UCET_INVALID",
            "Jméno účtu smí mít jen malá písmena bez diakritiky, číslice a pomlčku (např. 'sensio'); "
            "seznam účtů vrátí nástroj ucty_seznam.",
        )
    return ucet


# --- dukaz -------------------------------------------------------------------

def _hkdf_sha256(ikm: bytes, info: bytes, delka: int = 32) -> bytes:
    prk = hmac.new(b"\x00" * 32, ikm, hashlib.sha256).digest()
    okm, blok, i = b"", b"", 1
    while len(okm) < delka:
        blok = hmac.new(prk, blok + info + bytes([i]), hashlib.sha256).digest()
        okm += blok
        i += 1
    return okm[:delka]


def dukaz(uid: str, ucel: str, ucet: str, klic: bytes, ts: int) -> str:
    """Hodnota X-Kryton-Proof podle C3."""
    k = _hkdf_sha256(klic, HKDF_INFO)
    mac = hmac.new(k, f"{uid}\n{ts}\n{ucel}\n{ucet}".encode(), hashlib.sha256).hexdigest()
    return f"{uid}.{ts}.{mac}"


def _hlavicky(ucel: str, ucet: str) -> dict[str, str]:
    """Hlavicky pro jeden pozadavek: token, klic a id se ctou TED (rotace bez restartu)."""
    uid = users_id()
    token = nacti_token()
    klic = nacti_klic()
    return {"authorization": f"Bearer {token}", "x-kryton-proof": dukaz(uid, ucel, ucet, klic, int(time.time()))}


# --- prenos ------------------------------------------------------------------

_ZAKAZANE_HLAVICKY = {"authorization", "x-kryton-proof", "x-http-method-override", "x-http-method", "x-method-override"}


class GateHttp(httplib2.Http):
    """httplib2.Http, ktery mluvi jen s vratnym a ke kazdemu pozadavku prida token a dukaz."""

    def __init__(self, ucet: str):
        # proxy_info=None: httplib2 jinak bere http_proxy z prostredi a token pracovny by sel
        # pres proxy (revize B). Vratny je v siti pracovny, proxy k nemu nepatri.
        super().__init__(timeout=TIMEOUT_S, proxy_info=None)
        self.ucet = over_ucet(ucet)
        # 3xx se nenasleduje: vratny presmerovani Googlu nevraci (502 UPSTREAM_REDIRECT)
        # a kdyby prislo, token pracovny nesmi odejit na cizi adresu.
        self.follow_redirects = False

    def request(self, uri, method="GET", body=None, headers=None, redirections=0, connection_type=None):
        predpona = f"{gate_url()}/{self.ucet}/"
        if not isinstance(uri, str) or not uri.startswith(predpona):
            raise GateError(
                "GATE_HOST_REFUSED",
                "Požadavek mířil mimo vrátného Stáze a klient ho neodeslal (nahrávání a přesměrování "
                "režim vrátného nemá).",
            )
        zbytek = urllib.parse.urlsplit(uri[len(predpona):]).path
        if any(seg in (".", "..") for seg in zbytek.split("/")):
            # Knihovna id "." a ".." nekoduje (S1); klient je neposle, at nezalezi na normalizaci vratneho.
            raise GateError("PATH_INVALID", "Id '.' ani '..' nejde poslat (vrátný by cestu odmítl).")
        if any(k.lower() == "x-http-method-override" for k in (headers or {})):
            # googleapiclient prepise GET s adresou nad 2048 znaku na POST s touto hlavickou; vratny ji
            # zahodi a POST odmitne. Rict to rovnou a pravdive.
            raise GateError("REQUEST_TOO_LONG", "Dotaz je moc dlouhý (adresa nad 2048 znaků); zkrať ho.")
        h = {k: v for k, v in (headers or {}).items() if k.lower() not in _ZAKAZANE_HLAVICKY}
        h.update(_hlavicky(UCEL_TOKEN, self.ucet))
        try:
            return super().request(uri, method, body=body, headers=h, redirections=0,
                                   connection_type=connection_type)
        except http.client.HTTPException as e:
            raise GateError("GATE_BAD_RESPONSE", f"Vrátný Stáze odpověděl porušeně ({type(e).__name__}); zkus to za chvíli.") from None
        except (OSError, httplib2.HttpLib2Error, socket.timeout) as e:
            raise GateError(
                "GATE_UNREACHABLE",
                f"Vrátný Stáze v pracovně neodpovídá ({gate_url()}). Zkus to za chvíli; když to trvá, "
                f"napiš správci Red Dwarfu. ({type(e).__name__})",
            ) from None


def build_service(api: str, verze: str, ucet: str):
    """Sluzba Googlu postavena proti vratnemu. build() na sit nesaha (popis API je v balicku, S1)."""
    from googleapiclient import discovery

    sluzba, cesta = SLUZBY[(api, verze)]
    ucet = over_ucet(ucet)
    return discovery.build(
        api, verze,
        http=GateHttp(ucet),
        client_options={"api_endpoint": f"{gate_url()}/{ucet}/{sluzba}/{cesta}"},
        cache_discovery=False,
        static_discovery=True,
    )


# --- ucty --------------------------------------------------------------------

_ucty_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_ucty_zamek = threading.Lock()


def zapomen_ucty() -> None:
    with _ucty_zamek:
        _ucty_cache.clear()


def seznam_uctu(cerstvy: bool = False) -> list[dict]:
    """GET <GATE_URL>/_seznam (dukaz s ucelem person-accounts). Kratka pamet jen pro vychozi ucet."""
    zaklad, uid = gate_url(), users_id()
    klic_pameti = (zaklad, uid)
    with _ucty_zamek:
        hit = _ucty_cache.get(klic_pameti)
        if hit and not cerstvy and time.monotonic() - hit[0] < SEZNAM_PLATNOST_S:
            return hit[1]
    # Jmeno `spojeni`, ne `http`: lokalni `http` by zakrylo modul http (http.client.HTTPException
    # nize) a vypadek vratneho by skoncil AttributeError misto vety (revize A, kontrola oprav).
    spojeni = httplib2.Http(timeout=TIMEOUT_S, proxy_info=None)
    spojeni.follow_redirects = False
    try:
        resp, obsah = spojeni.request(f"{zaklad}/_seznam", "GET", headers=_hlavicky(UCEL_SEZNAM, ""), redirections=0)
    except http.client.HTTPException as e:
        raise GateError("GATE_BAD_RESPONSE", f"Vrátný Stáze odpověděl porušeně ({type(e).__name__}).") from None
    except (OSError, httplib2.HttpLib2Error, socket.timeout) as e:
        raise GateError(
            "GATE_UNREACHABLE",
            f"Vrátný Stáze v pracovně neodpovídá ({zaklad}). Zkus to za chvíli. ({type(e).__name__})",
        ) from None
    if resp.status != 200:
        raise chyba_z_odpovedi(resp, obsah, "")
    try:
        ucty = json.loads(obsah).get("ucty", [])
        assert isinstance(ucty, list)
    except Exception:  # noqa: BLE001
        raise GateError("GATE_BAD_RESPONSE", "Vrátný vrátil seznam účtů v neznámém tvaru.") from None
    with _ucty_zamek:
        _ucty_cache[klic_pameti] = (time.monotonic(), ucty)
    return ucty


def vyber_ucet(ucet: str | None) -> str:
    """Zadany ucet over; bez nej vezmi jediny zivy ucet cloveka, jinak chyba se seznamem."""
    if ucet:
        return over_ucet(ucet)
    zive = [u for u in seznam_uctu() if u.get("stav") == "active" and isinstance(u.get("ucet"), str)]
    if len(zive) == 1:
        return over_ucet(zive[0]["ucet"])
    if not zive:
        raise GateError(
            "NO_ACCOUNT",
            "Nemáš připojený žádný živý Google účet. Připoj ho: " + PRIPOJ.format(ucet="<jmeno>"),
        )
    jmena = ", ".join(f"{u['ucet']} ({u.get('email', '?')})" for u in zive)
    raise GateError("UCET_REQUIRED", f"Máš víc Google účtů, řekni který: parametr ucet = jedno z: {jmena}.")


# --- chyby -------------------------------------------------------------------

def _veta(kod: str, ucet: str, resp) -> str:
    u = ucet or "<jmeno>"
    retry = resp.get("retry-after", "") if resp is not None else ""
    schopnost = resp.get("x-trezor-capability", "") if resp is not None else ""
    vety = {
        "ACCOUNT_DISCONNECTED": f"Účet {u} je odpojený nebo mu vypršel souhlas. Připoj účet znovu: {PRIPOJ.format(ucet=u)}",
        "ACCOUNT_UNKNOWN": f"Účet {u} neznám. Své účty uvidíš nástrojem ucty_seznam.",
        "CAPABILITY_REQUIRED": f"Účet {u} tohle nesmí (chybí schopnost {schopnost or '?'}). "
                               "Ve vlně 1 jde jen čtení pošty, Disku a kalendáře a koncepty.",
        "PATH_NOT_ALLOWED": "Vrátný tuhle operaci nepouští: vlna 1 umí jen čtení pošty, Disku a kalendáře a koncepty.",
        "QUERY_NOT_ALLOWED": "Vrátný nepouští tenhle parametr dotazu (vlna 1 má pevný výčet).",
        "ALWAYS_DENIED": "Tohle vrátný nepustí nikdy (vlna 1: jen čtení a koncepty, žádné odeslání ani mazání).",
        "CONNECTIONS_DISABLED": "Připojení Google účtů je pro tvou firmu nebo platformu vypnuté.",
        "ADMIN_UNREACHABLE": "Vrátný se teď nedovolá ke správě účtů Red Dwarfu; zkus to za chvíli.",
        "NOT_READY": "Vrátný Stáze ještě není připravený; zkus to za chvíli.",
        "DAILY_CAP": f"Účet {u} vyčerpal denní strop volání. Zkus to znovu za {retry or '?'} s.",
        "MINUTE_CAP": f"Moc volání za minutu na účet {u}. Zkus to znovu za {retry or '?'} s.",
        "TOKEN_INVALID": "Vrátný nepřijal token Stáze této pracovny; napiš správci Red Dwarfu.",
        "TOKEN_REVOKED": "Vrátný hlásí, že token Stáze této pracovny byl odvolaný; napiš správci Red Dwarfu.",
        "PROOF_INVALID": "Vrátný nepřijal důkaz klíčem pracovny (klíč pracovny nebo hodiny); napiš správci Red Dwarfu.",
        "PATH_INVALID": "Vrátný odmítl tvar cesty (např. lomítko nebo '..' v id).",
        "BODY_TOO_LARGE": "Požadavek je na vrátného moc velký.",
        "UPSTREAM_REDIRECT": "Google odpověděl přesměrováním a vrátný ho nepustil.",
        "REFRESH_FAILED": "Správa účtů teď u Googlu neobnovila přístup; zkus to za chvíli.",
    }
    return vety.get(kod, f"Vrátný odmítl požadavek ({kod}).")


def chyba_z_odpovedi(resp, obsah, ucet: str) -> GateError:
    """Odpoved vratneho (X-Trezor-Reason) nebo Googlu prelozena na GateError."""
    kod = (resp.get("x-trezor-reason") or "").strip() if resp is not None else ""
    if kod:
        return GateError(kod, _veta(kod, ucet, resp))
    status = getattr(resp, "status", 0)
    zprava = ""
    try:
        zprava = json.loads(obsah).get("error", {}).get("message", "")
    except Exception:  # noqa: BLE001
        pass
    return GateError(f"GOOGLE_{status}", f"Google odpověděl {status}" + (f": {zprava}" if zprava else "."))


def preloz(e: Exception, ucet: str) -> GateError:
    """Jakakoli vyjimka nastroje na GateError s vetou pro cloveka."""
    if isinstance(e, GateError):
        return e
    from googleapiclient.errors import HttpError

    if isinstance(e, HttpError):
        return chyba_z_odpovedi(e.resp, e.content, ucet)
    # Cokoli jineho (KeyError z necekane odpovedi, chyba dekodovani...) je taky veta pro
    # cloveka, ne syrova vyjimka v MCP (zadani bod 4, revize B). Jen jmeno typu: text
    # vyjimky muze nest obsah zpravy nebo cestu s e-mailem.
    return GateError(
        "TOOL_ERROR",
        f"Nástroj nečekaně selhal ({type(e).__name__}). Zkus to znovu; když se to opakuje, napiš správci Red Dwarfu.",
    )
