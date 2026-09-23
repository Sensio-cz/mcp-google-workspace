"""
OAuth provider that proxies Google OAuth for multi-user authentication.
When claude.ai calls /authorize, the user is redirected to Google OAuth.
After Google login, the Google token travels INSIDE the issued MCP tokens.

BEZ PAMĚTI, A JE TO CELÝ SMYSL TOHOHLE SOUBORU. Dřív si provider držel
registrované klienty, auth kódy a vydané tokeny v `dict` a mapování na Google
tokeny v `/tmp`. Na Cloud Runu to znamenalo, že po uspání instance nebo při
druhé instanci server nepoznal token, který sám vydal - a každé volání
skončilo `invalid_token`, zatímco konektor v claude.ai ukazoval „Connected".

Teď každá hodnota nese svůj obsah zašifrovaná klíčem serveru (auth/sealed.py),
takže je jedno, která instance požadavek obslouží a kolikrát se služba
restartuje.

KLIENT SE V OSTATNÍCH HODNOTÁCH NESE JEN OTISKEM (`ch`), ne celým `client_id`.
`client_id` je samo zapečetěné, tedy dlouhé; kdyby se vkládalo do auth kódu
a tokenů, rostly by zbytečně. Otisk stačí: při každém volání SDK nejdřív načte
klienta podle `client_id` z požadavku a teprve pak nám ho podá k ověření.
"""

import hashlib
import logging
import time
from urllib.parse import urlencode

from pydantic import AnyUrl
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AccessToken,
    RefreshToken,
    OAuthAuthorizationServerProvider,
    TokenError,
)

from .sealed import zapecet, rozpecet
from .token_store import token_store, GOOGLE_SCOPES

logger = logging.getLogger(__name__)

# Token validity
ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 86400 * 30  # 30 days
# Kratka platnost je JEDINA obrana proti opakovanemu pouziti kodu: server si
# spotrebovane kody nepamatuje. Puvodni verze kod po vymene smazala z pameti
# instance - tam ho znovu pouzit neslo, na jine instanci ale kod vubec neznali,
# takze vymena selhala uplne. Je to tedy vedome prijate riziko, ne zachovani
# puvodniho chovani (upresneno po reviewu 22. 9. 2026). Klient kod vymenuje
# hned, minuta staci.
AUTH_CODE_TTL = 60

# STATE MA VLASTNI, DELSI PLATNOST NEZ AUTH KOD, protoze ceka na CLOVEKA:
# vyber uctu, heslo, dvoufazove overeni a souhlasna obrazovka se sesti scopy.
# Kdyz obe hodnoty sdilely jednu konstantu, zkraceni kodu na minutu zkratilo
# i okno na prihlaseni - a konektor pak koncil hlaskou "Invalid or expired
# state". Zmereno nezavislym reviewem 22. 9. 2026 (61 s uz neproslo).
STAV_TTL = 600  # 10 minut

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

# Druhy zapečetěných hodnot - v logu je vidět, o co jde, obsah ne.
D_KLIENT = "mcpc"
D_KOD = "mcpa"
D_PRISTUP = "mcpt"
D_OBNOVA = "mcpr"
D_STAV = "mcps"


def otisk_klienta(client_id: str) -> str:
    """Krátký otisk klienta do ostatních hodnot (viz hlavička)."""
    return hashlib.sha256(client_id.encode()).hexdigest()[:16]


class GoogleProxyOAuthProvider:
    """
    OAuth provider that redirects to Google OAuth during authorization.
    Maps MCP tokens to per-user Google tokens - bez serverové paměti.
    """

    def __init__(self, server_url: str, google_client_id: str, google_client_secret: str):
        self.server_url = server_url.rstrip("/")
        self.google_client_id = google_client_id
        self.google_client_secret = google_client_secret

    # --- Client Registration ---

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        udaje = rozpecet(D_KLIENT, client_id)
        if udaje is None:
            logger.info("Neznámý nebo neplatný client_id")
            return None
        return OAuthClientInformationFull(
            client_id=client_id,
            client_secret=udaje.get("cs"),
            client_name=udaje.get("n"),
            redirect_uris=[AnyUrl(u) for u in udaje.get("u", [])],
            grant_types=udaje.get("g", ["authorization_code", "refresh_token"]),
            response_types=udaje.get("rt", ["code"]),
            scope=udaje.get("s"),
            token_endpoint_auth_method=udaje.get("m", "client_secret_post"),
            client_id_issued_at=udaje.get("iat"),
            client_secret_expires_at=udaje.get("cse"),
        )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Registrace bez zápisu: client_id JE ta registrace, zapečetěná.

        Nedá se tedy „zapomenout" ani po restartu, a zároveň ji nejde podvrhnout
        - bez klíče serveru z ní nikdo nic nesestaví.
        """
        # SECRET PATRI DO ZAPECETENE REGISTRACE. Bez nej dostane klient, ktery
        # se hlasi metodou client_secret_post nebo _basic, na /token odpoved
        # `invalid_client` - SDK mu secret pri registraci vyda, ale server by
        # ho uz nikdy nepoznal. Zmereno reviewem 22. 9. 2026.
        client_info.client_id = zapecet(D_KLIENT, {
            "cs": client_info.client_secret,
            "cse": client_info.client_secret_expires_at,
            "n": client_info.client_name,
            "u": [str(u) for u in client_info.redirect_uris or []],
            "g": list(client_info.grant_types or []),
            "rt": list(client_info.response_types or []),
            "s": client_info.scope,
            "m": client_info.token_endpoint_auth_method,
        })
        client_info.client_id_issued_at = int(time.time())
        logger.info(f"Registered client: {client_info.client_name}")

    # --- Authorization (redirects to Google) ---

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """
        Instead of auto-approving, redirect user to Google OAuth.
        After Google login, /google/callback completes the MCP flow.

        Parametry MCP požadavku putují zapečetěné v `state`, který Google vrátí
        beze změny. Dřív ležely v paměti instance a callback, který dorazil na
        jinou instanci, je nenašel.
        """
        stav = zapecet(D_STAV, {
            "ch": otisk_klienta(client.client_id),
            "ci": client.client_id,
            "ru": str(params.redirect_uri) if params.redirect_uri else None,
            "rp": bool(params.redirect_uri_provided_explicitly),
            "cc": params.code_challenge,
            "sc": list(params.scopes or []),
            "r": str(params.resource) if params.resource else None,
            "st": params.state,
        }, platnost_s=STAV_TTL)

        google_params = {
            "client_id": self.google_client_id,
            "redirect_uri": f"{self.server_url}/google/callback",
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": stav,
        }
        logger.info("Redirecting to Google OAuth")
        return f"{GOOGLE_AUTH_URL}?{urlencode(google_params)}"

    def get_pending_auth(self, google_state: str) -> dict | None:
        """Parametry MCP požadavku ze `state`, který se vrátil od Googlu."""
        udaje = rozpecet(D_STAV, google_state)
        if udaje is None:
            logger.warning("Neplatný nebo prošlý state z Google callbacku")
            return None
        return {
            "client_id": udaje["ci"],
            "params": AuthorizationParams(
                state=udaje.get("st"),
                scopes=udaje.get("sc") or [],
                code_challenge=udaje.get("cc"),
                redirect_uri=AnyUrl(udaje["ru"]) if udaje.get("ru") else None,
                redirect_uri_provided_explicitly=bool(udaje.get("rp")),
                resource=udaje.get("r"),
            ),
        }

    def create_auth_code_for_client(
        self, client_id: str, params: AuthorizationParams, google: dict | None = None
    ) -> str:
        """Auth kód po úspěšném Google OAuth. Nese v sobě i Google refresh token.

        `google` = {"rt": refresh_token, "e": email}. Díky tomu nemusí server
        nikam ukládat mapování kód -> Google token; putuje s kódem a pak
        s vydanými tokeny.
        """
        return zapecet(D_KOD, {
            "ch": otisk_klienta(client_id),
            "ru": str(params.redirect_uri) if params.redirect_uri else None,
            "rp": bool(params.redirect_uri_provided_explicitly),
            "cc": params.code_challenge,
            "sc": list(params.scopes or []),
            "r": str(params.resource) if params.resource else None,
            "g": (google or {}).get("rt"),
            "e": (google or {}).get("e"),
        }, platnost_s=AUTH_CODE_TTL)

    # --- Authorization Code ---

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        udaje = rozpecet(D_KOD, authorization_code)
        if udaje is None or udaje.get("ch") != otisk_klienta(client.client_id):
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=udaje.get("sc") or [],
            expires_at=udaje.get("exp", 0),
            client_id=client.client_id,
            code_challenge=udaje.get("cc") or "",
            redirect_uri=AnyUrl(udaje["ru"]) if udaje.get("ru") else None,
            redirect_uri_provided_explicitly=bool(udaje.get("rp")),
            resource=udaje.get("r"),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        """Kód vymění za tokeny a PŘENESE do nich Google refresh token.

        KÓD JDE POUŽÍT VÍCKRÁT a je poctivé to napsat: server si spotřebované
        kódy nepamatuje. Chrání ho jen minutová platnost a PKCE, takže kdo kód
        zachytí i s `code_verifier`, vymění ho během té minuty znovu. Původní
        verze kód po výměně z paměti smazala, takže tohle je vědomě přijatá
        regrese výměnou za to, že tokeny přežijí restart. Skutečná jednorázovost
        by potřebovala sdílené úložiště (např. Firestore).
        """
        udaje = rozpecet(D_KOD, authorization_code.code) or {}
        obsah = {
            "ch": otisk_klienta(client.client_id),
            "sc": list(authorization_code.scopes or []),
            "r": str(authorization_code.resource) if authorization_code.resource else None,
            "g": udaje.get("g"),
            "e": udaje.get("e"),
        }
        # `rt0` = kdy retez obnovy zacal. Bez nej by kazda obnova posunula
        # platnost o dalsich 30 dni, takze kdo jednou ziska token obnovy, drzi
        # pristup navzdy. Nalez reviewu 22. 9. 2026 (mereno pres posunute hodiny).
        obsah["rt0"] = int(time.time())
        pristup = zapecet(D_PRISTUP, obsah, platnost_s=ACCESS_TOKEN_TTL)
        obnova = zapecet(D_OBNOVA, obsah, platnost_s=REFRESH_TOKEN_TTL)

        if udaje.get("e"):
            token_store.poznamenej_prihlaseni(udaje["e"])
        logger.info("Exchanged auth code for tokens")

        return OAuthToken(
            access_token=pristup,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=obnova,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    # --- Refresh Token ---

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        udaje = rozpecet(D_OBNOVA, refresh_token)
        if udaje is None or udaje.get("ch") != otisk_klienta(client.client_id):
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=udaje.get("sc") or [],
            expires_at=udaje.get("exp"),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        udaje = rozpecet(D_OBNOVA, refresh_token.token) or {}
        pouzite = scopes or refresh_token.scopes
        zacatek = int(udaje.get("rt0") or time.time())
        obsah = {
            "ch": otisk_klienta(client.client_id),
            "sc": list(pouzite or []),
            "r": udaje.get("r"),
            "g": udaje.get("g"),
            "e": udaje.get("e"),
            "rt0": zacatek,
        }
        # RETEZ NESMI PREZIT SVUJ ZACATEK O VIC NEZ REFRESH_TOKEN_TTL. Jinak by
        # se dal prodluzovat donekonecna a uniklý token by platil navzdy.
        zbyva = zacatek + REFRESH_TOKEN_TTL - int(time.time())
        if zbyva <= 0:
            # TokenError, ne ValueError: SDK chyta jen TokenError, takze cokoliv
            # jineho projde az ven jako HTTP 500. Trefit se da presne na vterine
            # vyprseni - zmereno reviewem 22. 9. 2026 s posunutymi hodinami.
            raise TokenError("invalid_grant", "refresh token chain expired")
        logger.info("Refreshed tokens")
        return OAuthToken(
            access_token=zapecet(D_PRISTUP, obsah, platnost_s=min(ACCESS_TOKEN_TTL, zbyva)),
            token_type="Bearer",
            expires_in=min(ACCESS_TOKEN_TTL, zbyva),
            refresh_token=zapecet(D_OBNOVA, obsah, platnost_s=zbyva),
            scope=" ".join(pouzite) if pouzite else None,
        )

    # --- Access Token Verification ---

    async def load_access_token(self, token: str) -> AccessToken | None:
        udaje = rozpecet(D_PRISTUP, token)
        if udaje is None:
            return None
        return AccessToken(
            token=token,
            client_id=udaje.get("ch", ""),
            scopes=udaje.get("sc") or [],
            expires_at=udaje.get("exp"),
            resource=udaje.get("r"),
        )

    # --- Revocation ---

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """ODVOLAT SE NEDÁ, a je poctivé to říct nahlas.

        Zapečetěný token platí, dokud nevyprší; server si seznam odvolaných
        nedrží, protože by to byla zase ta paměť, kvůli které tenhle soubor
        vznikl. Kdyby bylo potřeba odvolat všechno naráz, vymění se
        `MCP_TOKEN_KEY` - tím přestanou platit všechny tokeny najednou.
        Jednotlivé odvolání by potřebovalo sdílené úložiště (např. Firestore).
        """
        logger.warning("revoke_token: zapečetěné tokeny nejdou odvolat jednotlivě "
                       "(platnost vyprší sama; hromadně přes výměnu MCP_TOKEN_KEY)")
