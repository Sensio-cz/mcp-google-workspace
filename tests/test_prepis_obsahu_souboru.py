"""Prepis obsahu existujiciho souboru na Drive (0.4.0).

Drive konektor umel obsah jen nahrat jako novy soubor; uprava existujiciho Google
dokumentu tak znamenala novy soubor a novy odkaz. `update_file_content` vola
`files().update` s media uploadem na puvodni ID, takze odkaz zustava a Drive
nahrany HTML/text u Google dokumentu prevede.

Pojistky z revize 15. 10. 2026: vychozi text/html nesmi prepsat binarni soubor,
jine Google typy nez Docs/Sheets/Slides se odmitnou, expected_modified_time
chrani pred prepsanim cizi upravy.
"""
import base64
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from mcp_google_workspace.services.drive import DriveService

DOC = "application/vnd.google-apps.document"


def _service(mime_type=DOC, modified="2026-10-15T15:46:15.911Z"):
    svc = MagicMock()
    svc.files().get().execute.return_value = {
        "id": "F1", "name": "Smlouva", "mimeType": mime_type, "modifiedTime": modified, "version": "6",
    }
    svc.files().update().execute.return_value = {"id": "F1", "name": "Smlouva", "mimeType": mime_type, "version": "7"}
    svc.files.reset_mock()
    return svc


def _calls(svc, metoda):
    return [c for c in getattr(svc.files(), metoda).call_args_list if c.kwargs]


def _update_kwargs(svc):
    (call,) = _calls(svc, "update")
    return call.kwargs


def _prepis(svc, *args, **kwargs):
    with patch.object(DriveService, "service", new_callable=PropertyMock, return_value=svc):
        return DriveService().update_file_content(*args, **kwargs)


def test_html_se_posle_na_puvodni_id_jako_update():
    svc = _service()
    vysledek = _prepis(svc, "F1", "<p>Ahoj, čeština</p>")

    (get,) = _calls(svc, "get")
    assert get.kwargs["supportsAllDrives"] is True, "bez supportsAllDrives vraci get na sdilene soubory 404"
    kw = _update_kwargs(svc)
    assert kw["fileId"] == "F1", "obsah musi jit na puvodni ID, jinak vznikne novy soubor a novy odkaz"
    assert kw["supportsAllDrives"] is True
    assert "body" not in kw, "metadata (mimeType) se pri prepisu obsahu nemeni"
    media = kw["media_body"]
    assert media.mimetype() == "text/html"
    assert media.resumable() is False, "pod 5 MB jde jednoduchy upload (uploadType=media)"
    assert media.getbytes(0, media.size()) == "<p>Ahoj, čeština</p>".encode("utf-8")
    assert vysledek["version"] == "7"
    assert vysledek["previous"] == {
        "name": "Smlouva", "mimeType": DOC, "modifiedTime": "2026-10-15T15:46:15.911Z", "version": "6",
    }


def test_velky_obsah_jde_resumable_uploadem():
    svc = _service()
    _prepis(svc, "F1", "x" * (5 * 1024 * 1024 + 1), content_mime_type="text/plain")
    assert _update_kwargs(svc)["media_body"].resumable() is True


def test_base64_obsah_se_dekoduje_i_s_odradkovanim():
    svc = _service(mime_type="application/pdf")
    data = b"\x00\x01binarni" * 20
    b64 = base64.encodebytes(data).decode()  # MIME styl: odradkovani po 76 znacich
    assert "\n" in b64.strip()
    _prepis(svc, "F1", b64, content_mime_type="application/pdf", encoding="base64")
    media = _update_kwargs(svc)["media_body"]
    assert media.getbytes(0, media.size()) == data
    assert media.mimetype() == "application/pdf"


@pytest.mark.parametrize("typ", [
    "application/vnd.google-apps.folder",
    "application/vnd.google-apps.shortcut",
    "application/vnd.google-apps.form",
])
def test_jine_google_typy_odmitne_bez_zapisu(typ):
    svc = _service(mime_type=typ)
    vysledek = _prepis(svc, "F1", "<p>x</p>")
    assert vysledek["error"] is True
    assert not _calls(svc, "update"), "u slozky/zkratky se update nesmi zavolat"


def test_vychozi_html_neprepise_pdf():
    svc = _service(mime_type="application/pdf")
    vysledek = _prepis(svc, "F1", "<p>x</p>")
    assert vysledek["error"] is True
    assert "allow_type_change" in vysledek["message"]
    assert not _calls(svc, "update"), "text/html na PDF = znicene PDF; bez allow_type_change nic neposilat"


def test_zmena_typu_jde_jen_vyslovne():
    svc = _service(mime_type="application/pdf")
    vysledek = _prepis(svc, "F1", "<p>x</p>", allow_type_change=True)
    assert "error" not in vysledek
    assert _update_kwargs(svc)["media_body"].mimetype() == "text/html"


def test_soubor_zmeneny_mezitim_se_neprepise():
    svc = _service(modified="2026-10-15T16:00:00.000Z")
    vysledek = _prepis(svc, "F1", "<p>x</p>", expected_modified_time="2026-10-15T15:46:15.911Z")
    assert vysledek["error"] is True
    assert not _calls(svc, "update")

    svc = _service(modified="2026-10-15T15:46:15.911Z")
    vysledek = _prepis(svc, "F1", "<p>x</p>", expected_modified_time="2026-10-15T15:46:15.911Z")
    assert "error" not in vysledek


@pytest.mark.parametrize("content,encoding", [
    ("", "utf-8"), ("", "base64"), ("x", "latin-1"), ("to neni base64!", "base64"),
])
def test_prazdny_obsah_spatne_base64_nebo_cizi_encoding_skonci_chybou(content, encoding):
    svc = _service()
    with pytest.raises(ValueError):
        _prepis(svc, "F1", content, encoding=encoding)
    assert not _calls(svc, "update") and not _calls(svc, "get"), "chyba vstupu se pozna pred prvnim volanim API"
