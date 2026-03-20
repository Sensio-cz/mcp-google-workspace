import os
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from .auth.oauth_provider import InMemoryOAuthProvider

SERVER_URL = os.environ.get(
    "MCP_SERVER_URL",
    "https://mcp-google-workspace-581084999054.europe-west1.run.app",
)

oauth_provider = InMemoryOAuthProvider(server_url=SERVER_URL)

mcp = FastMCP(
    name="mcp-google-workspace",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8080")),
    auth_server_provider=oauth_provider,
    auth=AuthSettings(
        issuer_url=SERVER_URL,
        resource_server_url=SERVER_URL,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["mcp:tools"],
            default_scopes=["mcp:tools"],
        ),
        revocation_options=RevocationOptions(enabled=True),
    ),
)
