"""Komentare k souboru na Drive (0.5.0).

Server umel Doc jen precist nebo cely prepsat, komentar k dokumentu pridat nesel
(11. 11. 2026, pripominky k podkladu NetWalking Pro 2027). `create_comment` vola
`comments().create`. Google u Docs nepripne komentar zalozeny pres API ke
zvyraznenemu textu, proto se citat, ke kteremu komentar patri, vlozi na zacatek
textu komentare.
"""
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from mcp_google_workspace.services.drive import DriveService


def _service():
    svc = MagicMock()
    svc.comments().create().execute.return_value = {
        "id": "C1", "content": "x", "createdTime": "2026-11-11T10:00:00Z", "author": {"displayName": "Honza"},
    }
    svc.comments().list().execute.return_value = {
        "comments": [{"id": "C1", "content": "x", "resolved": False}],
    }
    svc.comments.reset_mock()
    return svc


def _kwargs(svc, metoda):
    calls = [c for c in getattr(svc.comments(), metoda).call_args_list if c.kwargs]
    (call,) = calls
    return call.kwargs


def _zavolej(svc, metoda, *args, **kwargs):
    with patch.object(DriveService, "service", new_callable=PropertyMock, return_value=svc):
        return getattr(DriveService(), metoda)(*args, **kwargs)


def test_komentar_jde_na_soubor_s_povinnym_fields():
    svc = _service()
    vysledek = _zavolej(svc, "create_comment", "F1", "Souhlasím.")

    kw = _kwargs(svc, "create")
    assert kw["fileId"] == "F1"
    assert kw["body"] == {"content": "Souhlasím."}
    assert kw["fields"], "comments API bez fields vraci 400"
    assert vysledek["id"] == "C1"


def test_citat_se_vlozi_na_zacatek_textu():
    svc = _service()
    _zavolej(svc, "create_comment", "F1", "Souhlasím.", quoted_text="Jedno důležité omezení.")

    assert _kwargs(svc, "create")["body"]["content"] == "K textu: „Jedno důležité omezení.“\n\nSouhlasím."


@pytest.mark.parametrize("obsah", ["", "   ", "\n"])
def test_prazdny_komentar_se_odmitne(obsah):
    svc = _service()
    with pytest.raises(ValueError):
        _zavolej(svc, "create_comment", "F1", obsah)
    assert not [c for c in svc.comments().create.call_args_list if c.kwargs]


def test_vypis_komentaru_vraci_seznam_a_pta_se_s_fields():
    svc = _service()
    vysledek = _zavolej(svc, "list_comments", "F1")

    kw = _kwargs(svc, "list")
    assert kw["fileId"] == "F1"
    assert kw["fields"]
    assert kw["includeDeleted"] is False
    assert vysledek == [{"id": "C1", "content": "x", "resolved": False}]
