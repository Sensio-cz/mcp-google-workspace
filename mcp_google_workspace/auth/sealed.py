"""
Zapečetěné hodnoty: token, který v sobě nese svůj vlastní obsah.

PROČ TO EXISTUJE. Server běží na Cloud Runu, který instanci po nečinnosti
uspí a při zátěži spustí další. Původní verze držela registrované klienty
a vydané tokeny v paměti instance (`dict`) a mapování na Google tokeny
v `/tmp/mcp-tokens.json`, což je souborový systém jedné instance. Jakmile
instance skončila nebo přibyla druhá, token, který si klient poctivě uložil,
už žádná instance neznala a každé volání skončilo `invalid_token`.
V Connectors přitom zůstala fajfka, protože ta je o tokenu u klienta, ne
o paměti serveru.

JAK TO ŘEŠÍ. Hodnota, kterou klient dostane, není odkaz do paměti, ale
zašifrovaný obsah sám. Kdokoliv ho rozbalí klíčem serveru, dostane všechno
potřebné. Server si tedy nemusí pamatovat nic a je jedno, která instance
požadavek obslouží.

BEZPEČNOST. Fernet = AES-128-CBC s HMAC-SHA256, takže obsah nejde ani
přečíst, ani podvrhnout bez klíče. Klíč je v proměnné `MCP_TOKEN_KEY`
a server bez něj vědomě **nenastartuje**: mlčky vygenerovaný klíč by po
každém nasazení odhlásil všechny uživatele, což je přesně ta porucha, kterou
tenhle soubor odstraňuje.

PLATNOST SE ŘÍDÍ POLEM `exp` UVNITŘ OBSAHU. Fernet sice nese i vlastní časovou
značku, ale `decrypt()` se tu volá bez `ttl`, takže se neověřuje - hodnota se
značkou z roku 1970 projde, pokud má platné `exp` (změřeno reviewem
22. 9. 2026). Hodnota bez `exp` platí navždy: tak je schválně zapečetěná
registrace klienta, kterou pak jde zneplatnit jedině výměnou klíče.
"""

import json
import logging
import os
import time

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENV_KLIC = "MCP_TOKEN_KEY"

_fernet: Fernet | None = None


class ChybiKlic(RuntimeError):
    """Server nemá čím pečetit. Fail-closed, ne tiché generování."""


def _sifra() -> Fernet:
    global _fernet
    if _fernet is None:
        hodnota = os.environ.get(ENV_KLIC, "").strip()
        if not hodnota:
            raise ChybiKlic(
                f"Chybí {ENV_KLIC}. Vygeneruj klíč příkazem\n"
                "  python -c \"from cryptography.fernet import Fernet;"
                "print(Fernet.generate_key().decode())\"\n"
                "a nastav ho jako proměnnou prostředí (na Cloud Runu ideálně přes Secret "
                "Manager). Bez něj by se tokeny po každém nasazení zneplatnily."
            )
        try:
            _fernet = Fernet(hodnota.encode())
        except Exception as e:  # noqa: BLE001
            raise ChybiKlic(
                f"{ENV_KLIC} není platný Fernet klíč (32 bajtů v urlsafe base64): {e}"
            ) from None
    return _fernet


def klic_je() -> bool:
    """Je čím pečetit? Volá se při startu, aby se chyba poznala hned."""
    try:
        _sifra()
        return True
    except ChybiKlic:
        return False


def zapecet(druh: str, data: dict, platnost_s: int | None = None) -> str:
    """Vrátí `<druh>_<zapečetěný obsah>`.

    DRUH JE UVNITŘ ŠIFROVANÉHO OBSAHU (`k`), předpona před podtržítkem je jen
    čitelné echo pro log. Kdyby druh žil jen v předponě, stačilo by ji přepsat
    a auth kód poslat jako token obnovy - podpis Fernetu chrání obsah, ne text
    před ním. Nalez nezávislého reviewu 22. 9. 2026, doložený měřením proti
    skutečnému `/token`: `mcpa_` přejmenované na `mcpr_` prošlo a vydalo
    třicetidenní token.
    """
    telo = dict(data)
    telo["k"] = druh
    telo["iat"] = int(time.time())
    if platnost_s is not None:
        telo["exp"] = int(time.time()) + platnost_s
    return f"{druh}_{_sifra().encrypt(json.dumps(telo, separators=(',', ':')).encode()).decode()}"


def rozpecet(druh: str, hodnota: str) -> dict | None:
    """Obsah, nebo None. None znamená: cizí, poškozené, jiného druhu, nebo prošlé.

    Volající nesmí rozlišovat proč - z odpovědi „tenhle token je po platnosti"
    proti „tenhle token není náš" se dá skládat útok.
    """
    if not hodnota or "_" not in hodnota:
        return None
    try:
        telo = json.loads(_sifra().decrypt(hodnota.split("_", 1)[1].encode()).decode())
    except (InvalidToken, ValueError, ChybiKlic):
        return None
    # ROZHODUJE DRUH ZEVNITR, ne předpona z požadavku. Předpona se schválně
    # vůbec neporovnává: kdo ji přepíše, narazí právě tady.
    if telo.get("k") != druh:
        return None
    exp = telo.get("exp")
    if exp is not None and time.time() > exp:
        return None
    return telo
