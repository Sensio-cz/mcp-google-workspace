import os

# REZIM VRATNEHO (pracovna Red Dwarfu, Stáze; kontrakt C5 planu gst-r253) zapina JEN
# promenna GOOGLE_WORKSPACE_GATE_URL. Staci, ze existuje: i prazdna hodnota znamena rezim
# vratneho a ten s ni odmitne nastartovat - tichy navrat k vlastnimu prihlaseni by
# v pracovne otevrel Google prihlaseni mimo Stázi. Bez promenne se nenaimportuje nic
# z rezimu vratneho a vse nize je beze zmeny (sluzba Sensia na Cloud Runu ji nema).
if "GOOGLE_WORKSPACE_GATE_URL" in os.environ:
    from .gate_app import main, mcp  # noqa: F401
else:
    from .server import mcp

    # Importy registruji tools pres @mcp.tool() decorator
    from .tools import gmail, drive, sheets, calendar  # noqa: F401

    def main():
        import sys

        # CLI: mcp-google-workspace --setup
        if "--setup" in sys.argv:
            from .auth.oauth_flow import run_oauth_flow
            from .auth.credentials import save_credentials
            from .config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
            print("Otviram prohlizec pro Google prihlaseni...")
            token_data = run_oauth_flow()
            save_credentials(
                refresh_token=token_data["refresh_token"],
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET,
            )
            print("Prihlaseni uspesne! MCP server je pripraven.")
            return

        transport = os.environ.get("MCP_TRANSPORT", "stdio")

        # KONTROLA KLICE PATRI SEM, NA START. Dokumentace tvrdila, ze bez
        # MCP_TOKEN_KEY server "nenastartuje" - neplatilo to: `klic_je()` sice bylo
        # v server.py naimportovane, ale nikde se nevolalo, takze proces nabehl,
        # /.well-known vracel 200 a rozbilo se to az uzivateli na `/register`
        # chybou 500 bez vysvetleni. Nasazeni pritom bylo zelene. Zmereno
        # nezavislym reviewem 23. 9. 2026.
        #
        # Stdio beh klic nepotrebuje: zadne MCP tokeny nevydava, Google credentials
        # bere ze souboru.
        if transport != "stdio":
            from .auth.sealed import klic_je

            if not klic_je():
                raise SystemExit(
                    "Chybi MCP_TOKEN_KEY. V rezimu "
                    f"MCP_TRANSPORT={transport} se jim pecetí vydavane tokeny, "
                    "takze bez nej skonci prvni prihlaseni chybou 500. "
                    "Vygenerovani a nasazeni klice: docs/nasazeni-a-klice.md."
                )

        mcp.run(transport=transport)


if __name__ == "__main__":
    main()
