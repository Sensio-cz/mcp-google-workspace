from typing import Any
from ..server import mcp
from ..services.drive import DriveService

_drive = None


def _get_drive() -> DriveService:
    global _drive
    if _drive is None:
        _drive = DriveService()
    return _drive


@mcp.tool()
async def drive_search_files(query: str, page_size: int = 10, shared_drive_id: str | None = None) -> dict[str, Any]:
    """Vyhledej soubory na Google Drive. Pouzij Drive query syntax (name contains 'x', mimeType='...')."""
    return {"files": _get_drive().search_files(query, page_size, shared_drive_id)}


@mcp.tool()
async def drive_read_file_content(file_id: str) -> dict[str, Any]:
    """Precti obsah souboru z Google Drive. Google Docs se exportuji jako markdown, Sheets jako CSV."""
    return _get_drive().read_file_content(file_id)


@mcp.tool()
async def drive_create_folder(folder_name: str, parent_folder_id: str | None = None, shared_drive_id: str | None = None) -> dict[str, Any]:
    """Vytvor slozku na Google Drive."""
    return _get_drive().create_folder(folder_name, parent_folder_id, shared_drive_id)


@mcp.tool()
async def drive_upload_file(filename: str, content_base64: str, parent_folder_id: str | None = None, shared_drive_id: str | None = None) -> dict[str, Any]:
    """Nahraj soubor na Google Drive. Obsah musi byt base64 encoded."""
    return _get_drive().upload_file(filename, content_base64, parent_folder_id, shared_drive_id)


@mcp.tool()
async def drive_delete_file(file_id: str) -> dict[str, Any]:
    """Smaz soubor z Google Drive."""
    return _get_drive().delete_file(file_id)


@mcp.tool()
async def drive_list_shared_drives(page_size: int = 100) -> dict[str, Any]:
    """Vypis sdilene disky na Google Drive."""
    return {"drives": _get_drive().list_shared_drives(page_size)}
