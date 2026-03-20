import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="mcp-google-workspace",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8080")),
)
