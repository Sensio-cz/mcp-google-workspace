import os
import asyncio
from .server import mcp

# Importy registruji tools pres @mcp.tool() decorator
from .tools import gmail, drive, sheets  # noqa: F401


def main():
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
