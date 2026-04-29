import os
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
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
