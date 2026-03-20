import base64
import hashlib
import http.server
import json
import os
import secrets
import urllib.parse
import urllib.request
import webbrowser

from ..config import GOOGLE_CLIENT_ID

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _generate_pkce() -> tuple[str, str]:
    """Generuj PKCE code_verifier a code_challenge (S256)."""
    code_verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def run_oauth_flow() -> dict:
    """Spusti OAuth PKCE flow - otevre prohlizec, uzivatel povoli pristup. Zadny Client Secret."""
    code_verifier, code_challenge = _generate_pkce()
    result = {}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            if "code" in params:
                # Vymenit code za token pomoci PKCE (bez client_secret)
                token_data = urllib.parse.urlencode({
                    "code": params["code"][0],
                    "client_id": GOOGLE_CLIENT_ID,
                    "redirect_uri": f"http://localhost:{self.server.server_address[1]}",
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                }).encode()

                req = urllib.request.Request(
                    "https://oauth2.googleapis.com/token",
                    data=token_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with urllib.request.urlopen(req) as resp:
                    token_response = json.loads(resp.read())

                result["refresh_token"] = token_response.get("refresh_token", "")
                result["access_token"] = token_response.get("access_token", "")

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    "<html><body><h1>Prihlaseni uspesne!</h1>"
                    "<p>Toto okno muzete zavrit.</p>"
                    "<script>window.close()</script>"
                    "</body></html>".encode("utf-8")
                )
            elif "error" in params:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                error = params.get("error", ["unknown"])[0]
                self.wfile.write(f"<h1>Chyba: {error}</h1>".encode("utf-8"))
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("localhost", 0), CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}"

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode({
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        })
    )

    print("Otviram prohlizec pro prihlaseni ke Google uctu...")
    print(f"Pokud se prohlizec neotevrel, navstivte: {auth_url}")
    webbrowser.open(auth_url)

    server.timeout = 120
    server.handle_request()
    server.server_close()

    if not result.get("refresh_token"):
        raise RuntimeError("OAuth flow selhal - nebyl ziskan refresh token")

    return result
