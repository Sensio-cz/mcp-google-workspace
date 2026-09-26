"""
Podpis patří přihlášenému uživateli a odpověď jde tomu, komu má.

PROČ TENHLE TEST EXISTUJE. Dvě chyby nalezené 26. 9. 2026 při napojení druhé
schránky (podpora MyCello) na stejný server:

1. `GmailService` je na serveru jedna pro všechny uživatele a podpis cachovala
   pod klíčem "primary". Do mailu kteréhokoli účtu se pak vkládal podpis toho,
   kdo na instanci poslal mail jako první.
2. Odpověď z webového formuláře šla na odesílatele formuláře (web@mycello.cz),
   protože nástroj uměl odpovídat jen na `from`. Zákaznice nedostala nic.

Spuštění: python -m pytest tests/test_gmail_podpis_a_adresat.py -q
"""

import base64
from email import message_from_bytes
from unittest.mock import MagicMock, patch

from mcp_google_workspace.services.gmail import GmailService


def _gmail_s_podpisem(podpis: str) -> MagicMock:
    api = MagicMock()
    api.users().settings().sendAs().list().execute.return_value = {
        "sendAs": [{"isPrimary": True, "signature": podpis}]
    }
    return api


def test_podpis_patri_aktualnimu_uzivateli():
    sluzba = GmailService()
    with patch.object(GmailService, "service", new=_gmail_s_podpisem("<b>Anna</b>")):
        assert sluzba.get_signature() == "<b>Anna</b>"
    with patch.object(GmailService, "service", new=_gmail_s_podpisem("<b>Petr</b>")):
        assert sluzba.get_signature() == "<b>Petr</b>"


def _odeslana_zprava(api: MagicMock):
    telo = api.users().messages().send.call_args.kwargs["body"]
    return telo, message_from_bytes(base64.urlsafe_b64decode(telo["raw"]))


def _puvodni(odesilatel: str) -> dict:
    return {
        "from": odesilatel, "to": "info@mycello.cz", "cc": "",
        "subject": "MyCello - Message from the contact form",
        "message_id": "<formular@mycello.cz>", "threadId": "vlakno-1",
    }


def test_odpoved_jde_na_zadanou_adresu_a_zustava_ve_vlakne():
    sluzba = GmailService()
    api = _gmail_s_podpisem("")
    with patch.object(GmailService, "service", new=api), \
         patch.object(GmailService, "get_email_by_id", return_value=_puvodni("MyCello <web@mycello.cz>")):
        sluzba.reply_to_email("e1", "Bonjour", send=True, to="zakaznice@example.fr")
    telo, zprava = _odeslana_zprava(api)
    assert zprava["To"] == "zakaznice@example.fr"
    assert telo["threadId"] == "vlakno-1"
    assert zprava["In-Reply-To"] == "<formular@mycello.cz>"


def test_bez_adresy_se_odpovida_odesilateli():
    sluzba = GmailService()
    api = _gmail_s_podpisem("")
    with patch.object(GmailService, "service", new=api), \
         patch.object(GmailService, "get_email_by_id", return_value=_puvodni("zakaznik@example.com")):
        sluzba.reply_to_email("e1", "Dobrý den", send=True)
    _, zprava = _odeslana_zprava(api)
    assert zprava["To"] == "zakaznik@example.com"
