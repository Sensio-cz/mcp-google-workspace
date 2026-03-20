import asyncio
from .server import mcp

# Importy registruji tools pres @mcp.tool() decorator
from .tools import gmail, drive, sheets  # noqa: F401


def main():
    asyncio.run(mcp.run())


if __name__ == "__main__":
    main()
