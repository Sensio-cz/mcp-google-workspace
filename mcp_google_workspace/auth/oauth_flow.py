import base64
import hashlib
import http.server
import json
import os
import secrets
import urllib.parse
import urllib.request
import webbrowser

from ..config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
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
                token_params = {
                    "code": params["code"][0],
                    "client_id": GOOGLE_CLIENT_ID,
                    "redirect_uri": f"http://localhost:{self.server.server_address[1]}",
                    "grant_type": "authorization_code",
                }
                if GOOGLE_CLIENT_SECRET:
                    token_params["client_secret"] = GOOGLE_CLIENT_SECRET
                else:
                    token_params["code_verifier"] = code_verifier
                token_data = urllib.parse.urlencode(token_params).encode()

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
                    """<html>
<head>
<meta charset="utf-8">
<title>Sensio MCP - Přihlášení</title>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Barlow', Arial, sans-serif; background: #f5f7fa; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { background: white; border-radius: 12px; padding: 48px; max-width: 440px; text-align: center; box-shadow: 0 4px 24px rgba(28,62,99,0.1); }
  .logo { color: #1C3E63; font-size: 28px; font-weight: 700; margin-bottom: 8px; }
  .logo span { color: #D67E29; }
  .check { width: 64px; height: 64px; background: #C5DB33; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 24px auto; }
  .check svg { width: 32px; height: 32px; stroke: white; stroke-width: 3; fill: none; }
  h1 { color: #1C3E63; font-size: 22px; font-weight: 600; margin-bottom: 12px; }
  p { color: #555; font-size: 15px; line-height: 1.5; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">sensio<span>.cz</span></div>
  <div class="check"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></div>
  <h1>Přihlášení úspěšné!</h1>
  <p>Toto okno můžete zavřít a pokračovat v práci s Claude.</p>
</div>
<script>setTimeout(function(){window.close()},3000)</script>
</body>
</html>""".encode("utf-8")
                )
            elif "error" in params:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                error = params.get("error", ["unknown"])[0]
                self.wfile.write(f"""<html>
<head>
<meta charset="utf-8">
<title>Sensio MCP - Chyba</title>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Barlow', Arial, sans-serif; background: #f5f7fa; display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
  .card {{ background: white; border-radius: 12px; padding: 48px; max-width: 440px; text-align: center; box-shadow: 0 4px 24px rgba(28,62,99,0.1); }}
  .logo {{ color: #1C3E63; font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
  .logo span {{ color: #D67E29; }}
  .icon {{ width: 64px; height: 64px; background: #D67E29; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 24px auto; }}
  .icon svg {{ width: 32px; height: 32px; stroke: white; stroke-width: 3; fill: none; }}
  h1 {{ color: #1C3E63; font-size: 22px; font-weight: 600; margin-bottom: 12px; }}
  p {{ color: #555; font-size: 15px; line-height: 1.5; }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">sensio<span>.cz</span></div>
  <div class="icon"><svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></div>
  <h1>Přihlášení se nezdařilo</h1>
  <p>Chyba: {error}<br>Zkuste to prosím znovu.</p>
</div>
</body>
</html>""".encode("utf-8")
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("localhost", 0), CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}"

    auth_params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    if not GOOGLE_CLIENT_SECRET:
        auth_params["code_challenge"] = code_challenge
        auth_params["code_challenge_method"] = "S256"

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode(auth_params)
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
