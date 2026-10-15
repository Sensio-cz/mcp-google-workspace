"""Prepis obsahu existujiciho souboru na Drive (0.4.0).

Drive konektor umel obsah jen nahrat jako novy soubor; uprava existujiciho Google
dokumentu tak znamenala novy soubor a novy odkaz. `update_file_content` vola
`files().update` s media uploadem na puvodni ID, takze odkaz zustava a Drive
nahrany HTML/text u Google dokumentu prevede.
"""
import base64
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from mcp_google_workspace.services.drive import DriveService


def _service(mime_type="application/vnd.google-apps.document"):
    svc = MagicMock()
    svc.files().get().execute.return_value = {"id": "F1", "name": "Smlouva", "mimeType": mime_type}
    svc.files().update().execute.return_value = {"id": "F1", "name": "Smlouva", "version": "7"}
    svc.files.reset_mock()
    return svc


def _update_kwargs(svc):
    (call,) = [c for c in svc.files().update.call_args_list if c.kwargs]
    return call.kwargs


def test_html_se_posle_na_puvodni_id_jako_update():
    svc = _service()
    with patch.object(DriveService, "service", new_callable=PropertyMock, return_value=svc):
        vysledek = DriveService().update_file_content("F1", "<p>Ahoj, čeština</p>")

    kw = _update_kwargs(svc)
    assert kw["fileId"] == "F1", "obsah musi jit na puvodni ID, jinak vznikne novy soubor a novy odkaz"
    assert kw["supportsAllDrives"] is True
    media = kw["media_body"]
    assert media.mimetype() == "text/html"
    assert media.getbytes(0, media.size()) == "<p>Ahoj, čeština</p>".encode("utf-8")
    assert vysledek["version"] == "7"


def test_base64_obsah_se_dekoduje():
    svc = _service(mime_type="text/plain")
    data = b"\x00\x01binarni"
    with patch.object(DriveService, "service", new_callable=PropertyMock, return_value=svc):
        DriveService().update_file_content(
            "F1", base64.b64encode(data).decode(), content_mime_type="application/octet-stream", encoding="base64"
        )
    media = _update_kwargs(svc)["media_body"]
    assert media.getbytes(0, media.size()) == data
    assert media.mimetype() == "application/octet-stream"


def test_slozku_odmitne_bez_zapisu():
    svc = _service(mime_type="application/vnd.google-apps.folder")
    with patch.object(DriveService, "service", new_callable=PropertyMock, return_value=svc):
        vysledek = DriveService().update_file_content("F1", "<p>x</p>")
    assert vysledek["error"] is True
    assert not [c for c in svc.files().update.call_args_list if c.kwargs], "u slozky se update nesmi zavolat"


@pytest.mark.parametrize("content,encoding", [("", "utf-8"), ("", "base64"), ("x", "latin-1")])
def test_prazdny_obsah_nebo_cizi_encoding_skonci_chybou(content, encoding):
    svc = _service()
    with patch.object(DriveService, "service", new_callable=PropertyMock, return_value=svc):
        with pytest.raises(ValueError):
            DriveService().update_file_content("F1", content, encoding=encoding)
    assert not [c for c in svc.files().update.call_args_list if c.kwargs]
