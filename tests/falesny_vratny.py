"""Falesny vratny (Stáze, kontrakt C4) pro testy rezimu vratneho.

Bezi na 127.0.0.1, zapisuje kazdy pozadavek a odpovida jako Google (data) nebo jako
vratny (chyby ve tvaru Googlu + hlavicka X-Trezor-Reason). Dukaz X-Kryton-Proof overuje
NEZAVISLOU implementaci (HKDF z balicku `cryptography`), ne kodem klienta - test tak
chyti chybu v klientove stavbe dukazu.

Sit ven je pri pouziti `zakaz_site_ven` zakazana: kazdy pokus o spojeni mimo 127.0.0.1
se zapise a odmitne.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def overeni_dukazu(klic: bytes, users_id: str, ucel: str, ucet: str, hodnota: str, okno: int = 60) -> bool:
    """Overi `<users_id>.<ts>.<mac>` podle C3, nezavisle na klientovi."""
    try:
        uid, ts, mac = hodnota.split(".")
    except ValueError:
        return False
    if uid != users_id or abs(int(ts) - int(time.time())) > okno:
        return False
    k = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"kryton-person-token-v1").derive(klic)
    ocekavano = hmac.new(k, f"{uid}\n{ts}\n{ucel}\n{ucet}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(ocekavano, mac)


class FalesnyVratny:
    """Stav falesneho vratneho; `chyby[(ucet, cesta_obsahuje)] = (http, kod, extra_hlavicky)`."""

    def __init__(self, klic: bytes, users_id: str = "42"):
        self.klic = klic
        self.users_id = users_id
        self.zaznamy: list[dict] = []
        self.ucty = [{"ucet": "sensio", "sluzba": "google", "email": "ja@sensio.cz",
                      "schopnosti": ["posta-cteni", "posta-koncepty", "disk-cteni", "kalendar-cteni"],
                      "stav": "active"}]
        self.chyby: dict[tuple[str, str], tuple[int, str, dict]] = {}
        self.obsah_zpravy = "Dobry den, posilam podklady."
        self.koncept_hlavicky = [
            {"name": "To", "value": "adresat@example.org"},
            {"name": "Subject", "value": "Re: Podklady"},
            {"name": "In-Reply-To", "value": "<m1@example.org>"},
            {"name": "References", "value": "<m1@example.org>"}]
        self.koncept_prilohy = False
        self.rozbita_zprava = False
        self.ucastnik = "kolega@sensio.cz"
        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self._srv.server_address[1]}/_osoba"
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    def zastav(self):
        self._srv.shutdown()
        self._srv.server_close()

    # --- odpovedi ---------------------------------------------------------

    def _chyba(self, http: int, kod: str, extra: dict | None = None):
        telo = json.dumps({"error": {"code": http, "message": f"vratny: {kod}", "status": kod}}).encode()
        h = {"Content-Type": "application/json"}
        if kod:
            h["X-Trezor-Reason"] = kod
        h.update(extra or {})
        return http, h, telo

    def _data(self, metoda: str, ucet: str, sluzba: str, cesta: str, dotaz: dict):
        j = lambda d: (200, {"Content-Type": "application/json"}, json.dumps(d).encode())  # noqa: E731
        b64 = lambda s: base64.urlsafe_b64encode(s.encode()).decode()  # noqa: E731
        if sluzba == "gmail":
            t = cesta.split("gmail/v1/users/me/", 1)[-1]
            if t == "messages" and metoda == "GET":
                return j({"messages": [{"id": "m1", "threadId": "t1"}]})
            if "/attachments/" in t:
                return j({"data": b64("obsah prilohy"), "size": 13})
            if t.startswith("messages/") and self.rozbita_zprava:
                return j({"id": "m1"})
            if t.startswith("messages/"):
                return j({"id": "m1", "threadId": "t1", "snippet": "s", "labelIds": ["INBOX"],
                          "payload": {"mimeType": "text/plain", "headers": [
                              {"name": "From", "value": "Cizi <cizi@example.org>"},
                              {"name": "To", "value": "ja@sensio.cz"},
                              {"name": "Subject", "value": "Podklady"},
                              {"name": "Message-Id", "value": "<m1@example.org>"}],
                              "body": {"data": b64(self.obsah_zpravy)}}})
            if t == "profile":
                return j({"emailAddress": "ja@sensio.cz"})
            if t == "drafts" and metoda == "POST":
                return j({"id": "d1", "message": {"id": "m9", "threadId": "t1"}})
            if t == "drafts" and metoda == "GET":
                return j({"drafts": [{"id": "d1", "message": {"id": "m9", "threadId": "t1"}}]})
            if t.startswith("drafts/"):
                if metoda == "DELETE":
                    return 204, {}, b""
                payload = {"mimeType": "text/plain", "headers": self.koncept_hlavicky,
                           "body": {"data": b64("puvodni koncept")}}
                if self.koncept_prilohy:
                    payload = {"mimeType": "multipart/mixed", "headers": self.koncept_hlavicky, "parts": [
                        {"mimeType": "text/plain", "body": {"data": b64("text")}},
                        {"mimeType": "application/pdf", "filename": "a.pdf", "body": {"attachmentId": "x"}}]}
                return j({"id": "d1", "message": {"id": "m9", "threadId": "t1", "payload": payload}})
        if sluzba == "drive":
            t = cesta.split("drive/v3/", 1)[-1]
            if t == "files":
                return j({"files": [{"id": "bin1", "name": "smlouva.pdf"}]})
            if t == "drives":
                return j({"drives": [{"id": "sd1", "name": "Sdileny"}]})
            if t.endswith("/comments"):
                return j({"comments": [{"id": "c1", "content": "komentar"}]})
            if t.endswith("/export"):
                return 200, {"Content-Type": "text/markdown"}, "# Dokument".encode()
            if t.startswith("files/"):
                fid = urllib.parse.unquote(t.split("/", 1)[1])
                if dotaz.get("alt") == ["media"]:
                    if fid == "cp1250":
                        return 200, {"Content-Type": "text/csv"}, "Příliš;žluťoučký".encode("cp1250")
                    return 200, {"Content-Type": "text/plain"}, "obsah souboru".encode()
                mime = {"doc1": "application/vnd.google-apps.document", "cp1250": "text/csv"}.get(fid, "text/plain")
                return j({"id": fid, "name": "n", "mimeType": mime})
        if sluzba == "calendar":
            t = cesta.split("calendar/v3/", 1)[-1]
            if t.startswith("users/me/calendarList"):
                return j({"items": [{"id": "primary", "summary": "Muj"}]})
            if "/events/" in t:
                return j({"id": "e1", "summary": "Porada"})
            if t.endswith("/events"):
                return j({"items": [{"id": "e1", "summary": "Porada", "attendees": [{"email": self.ucastnik}],
                                     "start": {"dateTime": "2026-11-23T10:00:00Z"},
                                     "end": {"dateTime": "2026-11-23T11:00:00Z"}}]})
        return self._chyba(403, "PATH_NOT_ALLOWED")

    def _handler(self):
        vratny = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _obsluz(self):
                n = int(self.headers.get("Content-Length") or 0)
                telo = self.rfile.read(n) if n else b""
                rozdel = urllib.parse.urlsplit(self.path)
                dotaz = urllib.parse.parse_qs(rozdel.query, keep_blank_values=True)
                cesta = rozdel.path
                zaznam = {"metoda": self.command, "cesta": cesta, "dotaz": dotaz,
                          "hlavicky": {k.lower(): v for k, v in self.headers.items()},
                          "telo": telo.decode("utf-8", "replace")}
                vratny.zaznamy.append(zaznam)
                status, hl, out = vratny._odpovez(zaznam)
                self.send_response(status)
                for k, v in hl.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _obsluz

        return H

    def _odpovez(self, z: dict):
        h = z["hlavicky"]
        if not h.get("authorization", "").startswith("Bearer "):
            return self._chyba(401, "TOKEN_INVALID")
        cesta = z["cesta"]
        if not cesta.startswith("/_osoba/"):
            return self._chyba(404, "PATH_INVALID")
        zbytek = cesta[len("/_osoba/"):]
        dukaz = h.get("x-kryton-proof", "")
        if zbytek == "_seznam":
            if not overeni_dukazu(self.klic, self.users_id, "person-accounts", "", dukaz):
                return self._chyba(401, "PROOF_INVALID")
            return 200, {"Content-Type": "application/json"}, json.dumps({"ucty": self.ucty}).encode()
        ucet, sluzba, google = (zbytek.split("/", 2) + ["", ""])[:3]
        if not overeni_dukazu(self.klic, self.users_id, "person-token", ucet, dukaz):
            return self._chyba(401, "PROOF_INVALID")
        for (u, kus), (http, kod, extra) in self.chyby.items():
            if u == ucet and kus in cesta:
                return self._chyba(http, kod, extra)
        return self._data(z["metoda"], ucet, sluzba, google, z["dotaz"])


class ZakazSite:
    """Kontextovy spravce: spojeni mimo 127.0.0.1 se odmitne a zapise do `pokusy`."""

    def __init__(self):
        self.pokusy: list[str] = []

    def __enter__(self):
        self._gai, self._cc = socket.getaddrinfo, socket.create_connection

        def gai(host, *a, **kw):
            if host not in ("127.0.0.1", "localhost"):
                self.pokusy.append(str(host))
                raise OSError(f"test: sit ven zakazana ({host})")
            return self._gai(host, *a, **kw)

        def cc(addr, *a, **kw):
            if addr[0] not in ("127.0.0.1", "localhost"):
                self.pokusy.append(str(addr[0]))
                raise OSError(f"test: sit ven zakazana ({addr[0]})")
            return self._cc(addr, *a, **kw)

        socket.getaddrinfo, socket.create_connection = gai, cc
        return self

    def __exit__(self, *exc):
        socket.getaddrinfo, socket.create_connection = self._gai, self._cc
        return False
